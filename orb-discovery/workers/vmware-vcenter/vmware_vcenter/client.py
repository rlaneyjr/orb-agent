#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""VMware vCenter REST API inventory client (hosts, clusters, VMs)."""

from __future__ import annotations

import logging
from typing import Any, Protocol

import httpx

from vmware_vcenter.models import ClusterInfo, ESXiHost, GuestVM

logger = logging.getLogger(__name__)

SESSION_PATH = "/api/session"
HOSTS_PATH = "/api/vcenter/host"
CLUSTERS_PATH = "/api/vcenter/cluster"
VMS_PATH = "/api/vcenter/vm"
SESSION_HEADER = "vmware-api-session-id"

# connection_state values treated as "active" when active_only=True.
ACTIVE_CONNECTION_STATES = frozenset({"connected"})
# power_state values treated as "active" for VMs when active_only=True.
ACTIVE_POWER_STATES = frozenset({"powered-on", "poweredon", "on"})


class InventoryClient(Protocol):
    """Fixture-friendly interface for listing vCenter inventory."""

    def list_clusters(self) -> list[ClusterInfo]:
        """Return cluster inventory from vCenter."""
        ...

    def list_devices(self, *, active_only: bool = True) -> list[ESXiHost]:
        """Return host inventory from vCenter."""
        ...

    def list_vms(self, *, active_only: bool = True) -> list[GuestVM]:
        """Return virtual machine inventory from vCenter."""
        ...


class VCenterClient:
    """
    HTTP client for the vSphere Automation REST inventory API.

    Authenticates with ``POST /api/session`` (HTTP Basic) and sends the returned
    session id as ``vmware-api-session-id``. Never log the password or session id.

    Inventory endpoints:
    - ``GET /api/vcenter/cluster``
    - ``GET /api/vcenter/host`` (optionally ``?clusters=``)
    - ``GET /api/vcenter/vm`` (optionally ``?clusters=`` / ``?hosts=``)
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
            host: Absolute vCenter base URL (no trailing slash).
            username: vCenter username (never logged with password).
            password: vCenter password (never logged).
            verify_ssl: Whether to verify TLS certificates.
            timeout: Request timeout in seconds.
            transport: Optional httpx transport (used in tests).

        """
        self._host = host.rstrip("/")
        self._timeout = timeout
        self._username = username
        self._password = password
        self._session_id: str | None = None
        self._clusters_cache: list[ClusterInfo] | None = None
        self._client = httpx.Client(
            base_url=self._host,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            verify=verify_ssl,
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        """Delete the API session (if any) and close the HTTP client."""
        if self._session_id is not None:
            try:
                self._client.delete(
                    SESSION_PATH,
                    headers={SESSION_HEADER: self._session_id},
                )
            except httpx.HTTPError:
                logger.debug("Failed to delete vCenter session for %s", self._host)
            self._session_id = None
        self._client.close()

    def __enter__(self) -> VCenterClient:
        """Enter context manager."""
        return self

    def __exit__(self, *args: object) -> None:
        """Exit context manager."""
        self.close()

    def list_clusters(self) -> list[ClusterInfo]:
        """Fetch clusters from vCenter inventory."""
        if self._clusters_cache is not None:
            return list(self._clusters_cache)

        records = self._get_list(CLUSTERS_PATH, label="clusters")
        clusters: list[ClusterInfo] = []
        for record in records:
            cluster = _record_to_cluster(record)
            if cluster is not None:
                clusters.append(cluster)

        self._clusters_cache = clusters
        logger.info("Fetched %d vCenter cluster(s) from %s", len(clusters), self._host)
        return list(clusters)

    def list_devices(self, *, active_only: bool = True) -> list[ESXiHost]:
        """Fetch ESXi hosts from vCenter inventory, enriched with cluster names."""
        clusters = self.list_clusters()
        host_cluster: dict[str, str] = {}
        for cluster in clusters:
            for record in self._get_list(
                HOSTS_PATH,
                label="hosts",
                params={"clusters": cluster.cluster_id},
            ):
                host_id = _optional_str(record.get("host"))
                if host_id:
                    host_cluster[host_id] = cluster.name

        records = self._get_list(HOSTS_PATH, label="hosts")
        devices: list[ESXiHost] = []
        for record in records:
            device = _record_to_host(record)
            if device is None:
                continue
            if device.device_id in host_cluster:
                device.cluster_name = host_cluster[device.device_id]
            if active_only and not _is_active_host(device.status):
                continue
            devices.append(device)

        logger.info(
            "Fetched %d vCenter host(s) from %s (active_only=%s)",
            len(devices),
            self._host,
            active_only,
        )
        return devices

    def list_vms(self, *, active_only: bool = True) -> list[GuestVM]:
        """Fetch virtual machines from vCenter inventory with cluster/host links."""
        vms_by_id = self._vms_by_cluster()
        self._apply_unfiltered_vms(vms_by_id)
        self._apply_host_placement(vms_by_id)

        vms = [
            vm
            for vm in vms_by_id.values()
            if not active_only or _is_active_vm(vm.power_state)
        ]

        logger.info(
            "Fetched %d vCenter VM(s) from %s (active_only=%s)",
            len(vms),
            self._host,
            active_only,
        )
        return vms

    def _vms_by_cluster(self) -> dict[str, GuestVM]:
        """Collect VMs keyed by id, annotated with cluster names."""
        vms_by_id: dict[str, GuestVM] = {}
        for cluster in self.list_clusters():
            for record in self._get_list(
                VMS_PATH,
                label="vms",
                params={"clusters": cluster.cluster_id},
            ):
                vm = _record_to_vm(record)
                if vm is None:
                    continue
                vm.cluster_name = cluster.name
                vms_by_id[vm.vm_id] = vm
        return vms_by_id

    def _apply_unfiltered_vms(self, vms_by_id: dict[str, GuestVM]) -> None:
        """Add VMs that are outside any cluster filter."""
        for record in self._get_list(VMS_PATH, label="vms"):
            vm = _record_to_vm(record)
            if vm is None or vm.vm_id in vms_by_id:
                continue
            vms_by_id[vm.vm_id] = vm

    def _apply_host_placement(self, vms_by_id: dict[str, GuestVM]) -> None:
        """Resolve VM → ESXi host placement via the hosts filter."""
        for host_record in self._get_list(HOSTS_PATH, label="hosts"):
            host_id = _optional_str(host_record.get("host"))
            host_name = _optional_str(host_record.get("name"))
            if not host_id or not host_name:
                continue
            for record in self._get_list(
                VMS_PATH,
                label="vms",
                params={"hosts": host_id},
            ):
                vm_id = _optional_str(record.get("vm"))
                if not vm_id:
                    continue
                if vm_id in vms_by_id:
                    vms_by_id[vm_id].host_name = host_name
                    continue
                vm = _record_to_vm(record)
                if vm is None:
                    continue
                vm.host_name = host_name
                vms_by_id[vm.vm_id] = vm

    def _ensure_session(self) -> str:
        """Create a vCenter API session if needed and return the session id."""
        if self._session_id is not None:
            return self._session_id

        response = self._client.post(
            SESSION_PATH,
            auth=(self._username, self._password),
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"vCenter session request failed: HTTP {exc.response.status_code}") from exc

        session_id = _parse_session_id(response)
        if not session_id:
            raise RuntimeError("vCenter session request failed: empty session id")
        self._session_id = session_id
        return session_id

    def _get_list(
        self,
        path: str,
        *,
        label: str,
        params: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """GET a vCenter list endpoint and return record dicts."""
        session_id = self._ensure_session()
        response = self._client.get(
            path,
            headers={SESSION_HEADER: session_id},
            params=params,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # Do not include response body — it may echo auth material.
            raise RuntimeError(f"vCenter {label} request failed: HTTP {exc.response.status_code}") from exc

        return _parse_list_payload(response.json() if response.content else None)


def _parse_session_id(response: httpx.Response) -> str | None:
    """Extract the session id from a POST /api/session response body."""
    if not response.content:
        return None
    try:
        payload = response.json()
    except ValueError:
        text = response.text.strip().strip('"')
        return text or None
    if isinstance(payload, str):
        text = payload.strip()
        return text or None
    return None


def _parse_list_payload(payload: Any) -> list[dict[str, Any]]:
    """Parse vCenter list responses (list or wrapped)."""
    if payload is None:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("value", "data", "items", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


# Keep the old name as an alias for tests that import it.
_parse_hosts_payload = _parse_list_payload


def _record_to_cluster(record: dict[str, Any]) -> ClusterInfo | None:
    """Map one vCenter Cluster.Summary record to a normalized ClusterInfo."""
    cluster_id = _optional_str(record.get("cluster"))
    name = _optional_str(record.get("name"))
    if not name:
        return None
    if not cluster_id:
        cluster_id = name

    return ClusterInfo(
        cluster_id=cluster_id,
        name=name,
        ha_enabled=_optional_bool(record.get("ha_enabled")),
        drs_enabled=_optional_bool(record.get("drs_enabled")),
    )


def _record_to_host(record: dict[str, Any]) -> ESXiHost | None:
    """Map one vCenter Host.Summary record to a normalized ESXiHost."""
    device_id = _optional_str(record.get("host"))
    hostname = _optional_str(record.get("name"))
    if not hostname:
        return None
    if not device_id:
        device_id = hostname

    return ESXiHost(
        device_id=device_id,
        hostname=hostname,
        status=_optional_str(record.get("connection_state")),
        power_state=_optional_str(record.get("power_state")),
        # Host.Summary does not include serial/model/mgmt IP; serial falls back to MOID in map.
        serial=None,
        model_name=None,
        mgmt_ip=None,
        software_version=None,
        cluster_name=None,
    )


def _record_to_vm(record: dict[str, Any]) -> GuestVM | None:
    """Map one vCenter VM.Summary record to a normalized GuestVM."""
    vm_id = _optional_str(record.get("vm"))
    name = _optional_str(record.get("name"))
    if not name:
        return None
    if not vm_id:
        vm_id = name

    return GuestVM(
        vm_id=vm_id,
        name=name,
        power_state=_optional_str(record.get("power_state")),
        cpu_count=_optional_int(record.get("cpu_count")),
        memory_mib=_optional_int(record.get("memory_size_MiB"))
        or _optional_int(record.get("memory_size_mib")),
        cluster_name=None,
        host_name=None,
    )


def _is_active_host(status: str | None) -> bool:
    """Return True when connection_state is missing (assume active) or CONNECTED."""
    if status is None or not status.strip():
        return True
    normalized = status.strip().lower().replace("_", "-").replace(" ", "-")
    if normalized in ACTIVE_CONNECTION_STATES:
        return True
    if any(marker in normalized for marker in ("disconnect", "not-responding", "offline", "down")):
        return False
    return True


def _is_active_vm(power_state: str | None) -> bool:
    """Return True when power_state is missing (assume active) or POWERED_ON."""
    if power_state is None or not power_state.strip():
        return True
    normalized = power_state.strip().lower().replace("_", "-").replace(" ", "-")
    if normalized in ACTIVE_POWER_STATES:
        return True
    if any(marker in normalized for marker in ("powered-off", "poweredoff", "off", "suspend")):
        return False
    return True


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


def _optional_bool(value: Any) -> bool | None:
    """Coerce a boolean-ish value, else None."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "1", "yes"):
            return True
        if lowered in ("false", "0", "no"):
            return False
    return None
