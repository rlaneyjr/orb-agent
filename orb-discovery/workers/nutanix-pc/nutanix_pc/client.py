#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""Nutanix Prism Central v3 inventory client (hosts, clusters, VMs)."""

from __future__ import annotations

import logging
from typing import Any, Protocol

import httpx

from nutanix_pc.models import ClusterInfo, GuestVM, PCHost

logger = logging.getLogger(__name__)

HOSTS_LIST_PATH = "/api/nutanix/v3/hosts/list"
CLUSTERS_LIST_PATH = "/api/nutanix/v3/clusters/list"
VMS_LIST_PATH = "/api/nutanix/v3/vms/list"

# Status values treated as "active" when active_only=True.
ACTIVE_STATUSES = frozenset(
    {
        "complete",
        "active",
        "online",
        "connected",
        "healthy",
        "up",
        "normal",
    }
)
ACTIVE_POWER_STATES = frozenset({"on", "powered-on", "poweredon", "running"})


class InventoryClient(Protocol):
    """Fixture-friendly interface for listing Prism Central inventory."""

    def list_clusters(self) -> list[ClusterInfo]:
        """Return cluster inventory from Prism Central."""
        ...

    def list_devices(self, *, active_only: bool = True) -> list[PCHost]:
        """Return host inventory from Prism Central."""
        ...

    def list_vms(self, *, active_only: bool = True) -> list[GuestVM]:
        """Return virtual machine inventory from Prism Central."""
        ...


class PrismCentralClient:
    """
    HTTP client for the Prism Central v3 inventory APIs.

    Authenticates with HTTP Basic (Prism username/password). Never log the
    password.

    Endpoints:
    - ``POST /api/nutanix/v3/clusters/list`` with body ``{"kind": "cluster"}``
    - ``POST /api/nutanix/v3/hosts/list`` with body ``{"kind": "host"}``
    - ``POST /api/nutanix/v3/vms/list`` with body ``{"kind": "vm"}``
    """

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        *,
        verify_ssl: bool = True,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """
        Construct the client.

        Args:
        ----
            host: Absolute Prism Central base URL (no trailing slash).
            username: Prism Central username (never logged with password).
            password: Prism Central password (never logged).
            verify_ssl: Whether to verify TLS certificates.
            timeout: Request timeout in seconds.
            transport: Optional httpx transport (used in tests).

        """
        self._host = host.rstrip("/")
        self._timeout = timeout
        self._client = httpx.Client(
            base_url=self._host,
            auth=(username, password),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            verify=verify_ssl,
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> PrismCentralClient:
        """Enter context manager."""
        return self

    def __exit__(self, *args: object) -> None:
        """Exit context manager."""
        self.close()

    def list_clusters(self) -> list[ClusterInfo]:
        """Fetch clusters from Prism Central inventory."""
        records = self._post_list(CLUSTERS_LIST_PATH, kind="cluster", label="clusters")
        clusters: list[ClusterInfo] = []
        for record in records:
            cluster = _record_to_cluster(record)
            if cluster is not None:
                clusters.append(cluster)

        logger.info("Fetched %d Prism Central cluster(s) from %s", len(clusters), self._host)
        return clusters

    def list_devices(self, *, active_only: bool = True) -> list[PCHost]:
        """Fetch physical hosts from Prism Central inventory."""
        records = self._post_list(HOSTS_LIST_PATH, kind="host", label="hosts")
        devices: list[PCHost] = []
        for record in records:
            device = _record_to_host(record)
            if device is None:
                continue
            if active_only and not _is_active(device.status):
                continue
            devices.append(device)

        logger.info(
            "Fetched %d Prism Central host(s) from %s (active_only=%s)",
            len(devices),
            self._host,
            active_only,
        )
        return devices

    def list_vms(self, *, active_only: bool = True) -> list[GuestVM]:
        """Fetch virtual machines from Prism Central inventory."""
        records = self._post_list(VMS_LIST_PATH, kind="vm", label="vms")
        vms: list[GuestVM] = []
        for record in records:
            vm = _record_to_vm(record)
            if vm is None:
                continue
            if active_only and not _is_active_vm(vm.power_state, vm.status):
                continue
            vms.append(vm)

        logger.info(
            "Fetched %d Prism Central VM(s) from %s (active_only=%s)",
            len(vms),
            self._host,
            active_only,
        )
        return vms

    def _post_list(self, path: str, *, kind: str, label: str) -> list[dict[str, Any]]:
        """POST a Prism Central */list endpoint and return entity dicts."""
        response = self._client.post(path, json={"kind": kind})
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # Do not include response body — it may echo auth material.
            raise RuntimeError(f"Prism Central {label} request failed: HTTP {exc.response.status_code}") from exc

        return _parse_entities_payload(response.json() if response.content else None)


def _parse_entities_payload(payload: Any) -> list[dict[str, Any]]:
    """Parse Prism Central */list responses."""
    if payload is None:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("entities", "data", "items", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


# Keep the old name as an alias for tests that import it.
_parse_hosts_payload = _parse_entities_payload


def _record_to_cluster(record: dict[str, Any]) -> ClusterInfo | None:
    """Map one Prism Central cluster entity to a normalized ClusterInfo."""
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    status = record.get("status") if isinstance(record.get("status"), dict) else {}
    spec = record.get("spec") if isinstance(record.get("spec"), dict) else {}

    cluster_id = _optional_str(metadata.get("uuid")) or _optional_str(record.get("uuid"))
    name = (
        _optional_str(status.get("name"))
        or _optional_str(spec.get("name"))
        or _optional_str(record.get("name"))
    )
    if not name:
        return None
    if not cluster_id:
        cluster_id = name

    return ClusterInfo(
        cluster_id=cluster_id,
        name=name,
        status=_optional_str(status.get("state")) or _optional_str(record.get("state")),
    )


def _record_to_host(record: dict[str, Any]) -> PCHost | None:
    """Map one Prism Central host entity to a normalized PCHost."""
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    status = record.get("status") if isinstance(record.get("status"), dict) else {}
    spec = record.get("spec") if isinstance(record.get("spec"), dict) else {}
    resources = {}
    if isinstance(status.get("resources"), dict):
        resources = status["resources"]
    elif isinstance(spec.get("resources"), dict):
        resources = spec["resources"]

    device_id = _optional_str(metadata.get("uuid")) or _optional_str(record.get("uuid"))
    hostname = (
        _optional_str(status.get("name"))
        or _optional_str(spec.get("name"))
        or _optional_str(record.get("name"))
        or _optional_str(resources.get("name"))
    )
    if not hostname:
        return None
    if not device_id:
        device_id = hostname

    hypervisor_info = resources.get("hypervisor") if isinstance(resources.get("hypervisor"), dict) else {}
    ipmi = resources.get("ipmi") if isinstance(resources.get("ipmi"), dict) else {}

    return PCHost(
        device_id=device_id,
        hostname=hostname,
        model_name=_first_str(
            resources,
            "block_model_name",
            "block_model",
            "rackable_unit_model_name",
            "model",
        ),
        software_version=_first_str(
            resources,
            "hypervisor_full_name",
            "hypervisor_version",
        )
        or _optional_str(hypervisor_info.get("full_name")),
        mgmt_ip=_first_str(resources, "hypervisor_ip", "external_ip", "ipmi_ip")
        or _optional_str(hypervisor_info.get("ip"))
        or _optional_str(ipmi.get("ip")),
        serial=_first_str(resources, "serial_number", "serial", "block_serial_number"),
        status=_optional_str(status.get("state")) or _optional_str(record.get("state")),
        cluster_name=_cluster_name_from_resources(resources),
        hypervisor=_first_str(resources, "hypervisor_type", "hypervisor_full_name")
        or _optional_str(hypervisor_info.get("type")),
    )


def _record_to_vm(record: dict[str, Any]) -> GuestVM | None:
    """Map one Prism Central VM entity to a normalized GuestVM."""
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    status = record.get("status") if isinstance(record.get("status"), dict) else {}
    spec = record.get("spec") if isinstance(record.get("spec"), dict) else {}
    resources = {}
    if isinstance(status.get("resources"), dict):
        resources = status["resources"]
    elif isinstance(spec.get("resources"), dict):
        resources = spec["resources"]

    vm_id = _optional_str(metadata.get("uuid")) or _optional_str(record.get("uuid"))
    name = (
        _optional_str(status.get("name"))
        or _optional_str(spec.get("name"))
        or _optional_str(record.get("name"))
    )
    if not name:
        return None
    if not vm_id:
        vm_id = name

    host_ref = resources.get("host_reference") if isinstance(resources.get("host_reference"), dict) else {}
    cluster_ref = (
        resources.get("cluster_reference") if isinstance(resources.get("cluster_reference"), dict) else {}
    )

    sockets = _optional_int(resources.get("num_sockets")) or 1
    vcpus_per_socket = _optional_int(resources.get("num_vcpus_per_socket"))
    cpu_count = None
    if vcpus_per_socket is not None:
        cpu_count = sockets * vcpus_per_socket
    elif _optional_int(resources.get("num_vcpus")) is not None:
        cpu_count = _optional_int(resources.get("num_vcpus"))

    return GuestVM(
        vm_id=vm_id,
        name=name,
        power_state=_optional_str(resources.get("power_state")),
        status=_optional_str(status.get("state")) or _optional_str(record.get("state")),
        cpu_count=cpu_count,
        memory_mib=_optional_int(resources.get("memory_size_mib")),
        disk_gb=_disk_gb_from_resources(resources),
        cluster_name=_optional_str(cluster_ref.get("name")) or _cluster_name_from_resources(resources),
        host_name=_optional_str(host_ref.get("name")),
        primary_ip=_primary_ip_from_resources(resources),
    )


def _cluster_name_from_resources(resources: dict[str, Any]) -> str | None:
    """Extract a cluster name from host/VM resources."""
    name = _first_str(resources, "cluster_name", "cluster")
    if name:
        return name
    cluster_ref = resources.get("cluster_reference")
    if isinstance(cluster_ref, dict):
        return _optional_str(cluster_ref.get("name"))
    return None


def _disk_gb_from_resources(resources: dict[str, Any]) -> int | None:
    """Sum VM disk sizes and convert to whole GiB."""
    disk_list = resources.get("disk_list")
    if not isinstance(disk_list, list):
        return None
    total_mib = 0
    found = False
    for disk in disk_list:
        if not isinstance(disk, dict):
            continue
        mib = _optional_int(disk.get("disk_size_mib"))
        if mib is None:
            bytes_size = _optional_int(disk.get("disk_size_bytes"))
            if bytes_size is not None:
                mib = bytes_size // (1024 * 1024)
        if mib is not None:
            total_mib += mib
            found = True
    if not found:
        return None
    return max(total_mib // 1024, 0)


def _primary_ip_from_resources(resources: dict[str, Any]) -> str | None:
    """Return the first IPv4-looking NIC endpoint from a VM."""
    nic_list = resources.get("nic_list")
    if not isinstance(nic_list, list):
        return None
    for nic in nic_list:
        if not isinstance(nic, dict):
            continue
        endpoints = nic.get("ip_endpoint_list")
        if not isinstance(endpoints, list):
            continue
        for endpoint in endpoints:
            if not isinstance(endpoint, dict):
                continue
            ip = _optional_str(endpoint.get("ip"))
            if ip and _looks_like_ipv4(ip):
                return ip
    return None


def _is_active(status: str | None) -> bool:
    """Return True when status is missing (assume active) or an active value."""
    if status is None or not status.strip():
        return True
    normalized = status.strip().lower().replace("_", "-").replace(" ", "-")
    if normalized in ACTIVE_STATUSES:
        return True
    if any(marker in normalized for marker in ("offline", "disconnect", "down", "fail", "inactive", "error")):
        return False
    return True


def _is_active_vm(power_state: str | None, status: str | None) -> bool:
    """Return True when the VM appears powered on / complete."""
    if power_state is not None and power_state.strip():
        normalized = power_state.strip().lower().replace("_", "-").replace(" ", "-")
        if normalized in ACTIVE_POWER_STATES:
            return True
        if any(marker in normalized for marker in ("off", "power-off", "powered-off", "suspend")):
            return False
    return _is_active(status)


def _first_str(record: dict[str, Any], *keys: str) -> str | None:
    """Return the first present non-empty string for the given keys."""
    for key in keys:
        if key in record:
            text = _optional_str(record.get(key))
            if text is not None:
                return text
    return None


def _optional_str(value: Any) -> str | None:
    """Coerce a non-empty value to str, else None."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    """Coerce a numeric value to int, else None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _looks_like_ipv4(value: str) -> bool:
    """Return True for a simple dotted-quad IPv4 string."""
    parts = value.split(".")
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(part) <= 255 for part in parts)
    except ValueError:
        return False
