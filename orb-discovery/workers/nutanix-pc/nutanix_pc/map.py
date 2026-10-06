#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""Map Prism Central inventory records to Diode entities."""

from __future__ import annotations

import logging
from collections.abc import Iterable

from netboxlabs.diode.sdk.ingester import Cluster, ClusterType, Device, Entity, VirtualMachine

from nutanix_pc.client import ACTIVE_POWER_STATES, ACTIVE_STATUSES
from nutanix_pc.models import ClusterInfo, Defaults, GuestVM, PCHost

logger = logging.getLogger(__name__)


def map_inventory(
    clusters: Iterable[ClusterInfo],
    devices: Iterable[PCHost],
    vms: Iterable[GuestVM],
    defaults: Defaults,
) -> list[Entity]:
    """
    Convert Prism Central clusters, hosts, and VMs into Diode entities.

    Emits Cluster → Device → VirtualMachine so Diode can resolve references.
    Clusters referenced only by hosts/VMs are synthesized when missing.
    """
    device_list = list(devices)
    vm_list = list(vms)
    cluster_list = _merge_cluster_refs(clusters, device_list, vm_list)

    entities: list[Entity] = []
    entities.extend(map_clusters(cluster_list, defaults))
    entities.extend(map_devices(device_list, defaults))
    entities.extend(map_vms(vm_list, defaults))
    return entities


def _merge_cluster_refs(
    clusters: Iterable[ClusterInfo],
    devices: Iterable[PCHost],
    vms: Iterable[GuestVM],
) -> list[ClusterInfo]:
    """Ensure every referenced cluster name has a ClusterInfo record."""
    by_name: dict[str, ClusterInfo] = {}
    for cluster in clusters:
        name = (cluster.name or "").strip()
        if name:
            by_name[name] = cluster
    for obj in [*devices, *vms]:
        name = (getattr(obj, "cluster_name", None) or "").strip()
        if name and name not in by_name:
            by_name[name] = ClusterInfo(cluster_id=name, name=name)
    return list(by_name.values())


def map_clusters(clusters: Iterable[ClusterInfo], defaults: Defaults) -> list[Entity]:
    """Convert Prism Central clusters into Diode Cluster entities."""
    entities: list[Entity] = []
    seen: set[str] = set()
    for cluster in clusters:
        entity = map_cluster(cluster, defaults)
        if entity is None:
            continue
        name = entity.cluster.name
        if name in seen:
            continue
        seen.add(name)
        entities.append(entity)
    return entities


def map_cluster(cluster: ClusterInfo, defaults: Defaults) -> Entity | None:
    """Map a single Prism Central cluster to a Diode Entity."""
    name = (cluster.name or "").strip()
    if not name:
        logger.warning("Skipping Prism Central cluster without name (id=%s)", cluster.cluster_id)
        return None

    diode_cluster = Cluster(
        name=name,
        type=ClusterType(name=defaults.cluster_type),
        scope_site=defaults.site,
        status=_status_from_pc(cluster.status),
        tags=list(defaults.tags) if defaults.tags else None,
    )
    return Entity(cluster=diode_cluster)


def map_devices(devices: Iterable[PCHost], defaults: Defaults) -> list[Entity]:
    """Convert Prism Central hosts into Diode Device entities."""
    entities: list[Entity] = []
    for device in devices:
        entity = map_device(device, defaults)
        if entity is not None:
            entities.append(entity)
    return entities


def map_device(device: PCHost, defaults: Defaults) -> Entity | None:
    """Map a single Prism Central host to a Diode Entity."""
    name = (device.hostname or "").strip()
    if not name:
        logger.warning("Skipping Prism Central host without hostname (id=%s)", device.device_id)
        return None

    status = _status_from_pc(device.status)
    description_parts = []
    if device.software_version:
        description_parts.append(device.software_version)
    if device.hypervisor:
        description_parts.append(f"hypervisor={device.hypervisor}")
    if device.mgmt_ip:
        description_parts.append(f"mgmt={device.mgmt_ip}")

    serial = (device.serial or device.device_id or "").strip() or None
    cluster_name = (device.cluster_name or "").strip() or None

    diode_device = Device(
        name=name,
        device_type=device.model_name or "unknown",
        manufacturer=defaults.manufacturer,
        platform=defaults.platform,
        site=defaults.site,
        role=defaults.role,
        serial=serial,
        status=status,
        cluster=cluster_name,
        description="; ".join(description_parts) if description_parts else None,
        tags=list(defaults.tags) if defaults.tags else None,
        primary_ip4=device.mgmt_ip if _looks_like_ipv4(device.mgmt_ip) else None,
    )
    return Entity(device=diode_device)


def map_vms(vms: Iterable[GuestVM], defaults: Defaults) -> list[Entity]:
    """Convert Prism Central VMs into Diode VirtualMachine entities."""
    entities: list[Entity] = []
    for vm in vms:
        entity = map_vm(vm, defaults)
        if entity is not None:
            entities.append(entity)
    return entities


def map_vm(vm: GuestVM, defaults: Defaults) -> Entity | None:
    """Map a single Prism Central VM to a Diode Entity."""
    name = (vm.name or "").strip()
    if not name:
        logger.warning("Skipping Prism Central VM without name (id=%s)", vm.vm_id)
        return None

    status = _status_from_pc_vm(vm.power_state, vm.status)
    cluster_name = (vm.cluster_name or "").strip() or None
    host_name = (vm.host_name or "").strip() or None

    diode_vm = VirtualMachine(
        name=name,
        status=status,
        site=defaults.site,
        cluster=cluster_name,
        device=host_name,
        role=defaults.vm_role,
        platform=defaults.vm_platform,
        vcpus=float(vm.cpu_count) if vm.cpu_count is not None else None,
        memory=vm.memory_mib,
        disk=vm.disk_gb,
        primary_ip4=vm.primary_ip if _looks_like_ipv4(vm.primary_ip) else None,
        tags=list(defaults.tags) if defaults.tags else None,
    )
    return Entity(virtual_machine=diode_vm)


def _status_from_pc(status: str | None) -> str:
    """Map Prism Central state to a NetBox status."""
    if status is None or not status.strip():
        return "active"
    normalized = status.strip().lower().replace("_", "-").replace(" ", "-")
    if normalized in ACTIVE_STATUSES:
        return "active"
    if any(marker in normalized for marker in ("offline", "disconnect", "down", "fail", "inactive", "error")):
        return "offline"
    return "active"


def _status_from_pc_vm(power_state: str | None, status: str | None) -> str:
    """Map Prism Central VM power/state to a NetBox VM status."""
    if power_state is not None and power_state.strip():
        normalized = power_state.strip().lower().replace("_", "-").replace(" ", "-")
        if normalized in ACTIVE_POWER_STATES:
            return "active"
        if any(marker in normalized for marker in ("off", "power-off", "powered-off", "suspend")):
            return "offline"
    return _status_from_pc(status)


def _looks_like_ipv4(value: str | None) -> bool:
    """Return True for a simple dotted-quad IPv4 string."""
    if not value:
        return False
    parts = value.split(".")
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(part) <= 255 for part in parts)
    except ValueError:
        return False
