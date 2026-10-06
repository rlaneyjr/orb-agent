#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""Map vCenter ESXi host records to Diode entities."""

from __future__ import annotations

import logging
from collections.abc import Iterable

from netboxlabs.diode.sdk.ingester import Device, Entity

from vmware_vcenter.client import ACTIVE_CONNECTION_STATES
from vmware_vcenter.models import Defaults, ESXiHost

logger = logging.getLogger(__name__)

# TODO(future): also emit Diode Cluster / ClusterType and VirtualMachine entities
# (and link VM→host/cluster). Guest VMs and clusters are deferred beyond this MVP.


def map_devices(devices: Iterable[ESXiHost], defaults: Defaults) -> list[Entity]:
    """Convert vCenter ESXi hosts into Diode Device entities."""
    entities: list[Entity] = []
    for device in devices:
        entity = map_device(device, defaults)
        if entity is not None:
            entities.append(entity)
    return entities


def map_device(device: ESXiHost, defaults: Defaults) -> Entity | None:
    """Map a single vCenter ESXi host to a Diode Entity."""
    name = (device.hostname or "").strip()
    if not name:
        logger.warning("Skipping vCenter host without hostname (id=%s)", device.device_id)
        return None

    status = _status_from_vcenter(device.status)
    description_parts = []
    if device.software_version:
        description_parts.append(device.software_version)
    if device.power_state:
        description_parts.append(f"power={device.power_state}")
    if device.mgmt_ip:
        description_parts.append(f"mgmt={device.mgmt_ip}")
    if device.cluster_name:
        description_parts.append(f"cluster={device.cluster_name}")

    serial = (device.serial or device.device_id or "").strip() or None

    diode_device = Device(
        name=name,
        device_type=device.model_name or "unknown",
        manufacturer=defaults.manufacturer,
        platform=defaults.platform,
        site=defaults.site,
        role=defaults.role,
        serial=serial,
        status=status,
        description="; ".join(description_parts) if description_parts else None,
        tags=list(defaults.tags) if defaults.tags else None,
        primary_ip4=device.mgmt_ip if _looks_like_ipv4(device.mgmt_ip) else None,
    )
    return Entity(device=diode_device)


def _status_from_vcenter(status: str | None) -> str:
    """Map vCenter connection_state to a NetBox device status."""
    if status is None or not status.strip():
        return "active"
    normalized = status.strip().lower().replace("_", "-").replace(" ", "-")
    if normalized in ACTIVE_CONNECTION_STATES:
        return "active"
    if any(marker in normalized for marker in ("disconnect", "not-responding", "offline", "down")):
        return "offline"
    return "active"


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
