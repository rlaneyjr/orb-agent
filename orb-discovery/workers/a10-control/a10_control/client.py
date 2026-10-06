#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""A10 Control ACAPI client (organization-scoped inventory)."""

from __future__ import annotations

import logging
from typing import Any, Protocol

import httpx

from a10_control.models import A10Device

logger = logging.getLogger(__name__)

DEVICES_PATH = "/device/"
CLUSTERS_PATH = "/cluster/"
ACAPI_PREFIX = "/api/v2/acapi/v1/organization"

# Status values treated as "active" when active_only=True.
ACTIVE_STATUSES = frozenset(
    {
        "active",
        "online",
        "connected",
        "registered",
        "ready",
        "up",
        "healthy",
        "provisioned",
    }
)


class InventoryClient(Protocol):
    """Fixture-friendly interface for listing A10 Control devices."""

    def list_devices(self, *, active_only: bool = True) -> list[A10Device]:
        """Return inventory devices from A10 Control."""
        ...


class A10ControlClient:
    """
    HTTP client for the A10 Control organization ACAPI.

    Base URL shape (from A10 Control OpenAPI):

        https://{host}/api/v2/acapi/v1/organization/{organization}

    Authentication uses the organization API key as ``x-api-key`` (see A10
    Control API Reference Guide). Never log the API key.
    """

    def __init__(
        self,
        host: str,
        api_key: str,
        organization: str,
        *,
        verify_ssl: bool = True,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """
        Construct the client.

        Args:
        ----
            host: Absolute A10 Control base URL (no trailing slash).
            api_key: Organization API key (never logged).
            organization: Organization name used in the ACAPI path.
            verify_ssl: Whether to verify TLS certificates.
            timeout: Request timeout in seconds.
            transport: Optional httpx transport (used in tests).

        """
        self._host = host.rstrip("/")
        self._organization = organization
        self._timeout = timeout
        self._base_path = f"{ACAPI_PREFIX}/{organization}"
        self._client = httpx.Client(
            base_url=self._host,
            headers={
                "x-api-key": api_key,
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

    def __enter__(self) -> A10ControlClient:
        """Enter context manager."""
        return self

    def __exit__(self, *args: object) -> None:
        """Exit context manager."""
        self.close()

    def list_devices(self, *, active_only: bool = True) -> list[A10Device]:
        """
        Fetch devices from A10 Control inventory.

        Primary path: ``GET .../device/`` (collection companion to the documented
        ``GET .../device/{device_id}``). If that returns empty or 404, fall back to
        extracting devices from ``GET .../cluster/`` cluster-list payloads.
        """
        records = self._fetch_device_records()
        devices: list[A10Device] = []
        for record in records:
            device = _record_to_device(record)
            if device is None:
                continue
            if active_only and not _is_active(device.status):
                continue
            devices.append(device)

        logger.info(
            "Fetched %d A10 Control device(s) from %s org=%s (active_only=%s)",
            len(devices),
            self._host,
            self._organization,
            active_only,
        )
        return devices

    def _fetch_device_records(self) -> list[dict[str, Any]]:
        """Load device records from /device/ or cluster inventory fallback."""
        path = f"{self._base_path}{DEVICES_PATH}"
        response = self._client.get(path)
        if response.status_code == 404:
            logger.info("A10 Control /device/ not found; falling back to /cluster/")
            return self._devices_from_clusters()
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # Do not include response body — it may echo auth material.
            raise RuntimeError(f"A10 Control inventory request failed: HTTP {exc.response.status_code}") from exc

        records = _parse_device_payload(response.json() if response.content else None)
        if records:
            return records
        # Some Controllers only expose devices under cluster objects.
        return self._devices_from_clusters()

    def _devices_from_clusters(self) -> list[dict[str, Any]]:
        """List clusters and flatten embedded device objects."""
        path = f"{self._base_path}{CLUSTERS_PATH}"
        response = self._client.get(path, params={"summary": "false"})
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"A10 Control cluster request failed: HTTP {exc.response.status_code}") from exc

        payload = response.json() if response.content else None
        return _devices_from_cluster_payload(payload)


def _parse_device_payload(payload: Any) -> list[dict[str, Any]]:
    """Parse list / wrapped device inventory responses."""
    if payload is None:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    for key in ("device-list", "devices", "device", "data", "items", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            # Single device wrapped as {"device": {...}}
            return [value]
    # Single device object
    if _looks_like_device(payload):
        return [payload]
    return []


def _devices_from_cluster_payload(payload: Any) -> list[dict[str, Any]]:
    """Extract device dicts from GET /cluster/ responses."""
    clusters = _extract_cluster_list(payload)
    if clusters is None:
        return [payload] if isinstance(payload, dict) and _looks_like_device(payload) else []

    devices: list[dict[str, Any]] = []
    for cluster in clusters:
        devices.extend(_devices_from_cluster(cluster))
    return devices


def _extract_cluster_list(payload: Any) -> list[dict[str, Any]] | None:
    """Return cluster objects from a /cluster/ payload, or None if unusable."""
    if payload is None:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("cluster-list", "clusters", "data", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return None


def _devices_from_cluster(cluster: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten devices embedded in one cluster object."""
    cluster_name = _optional_str(cluster.get("name") or cluster.get("display-name"))
    cluster_id = _optional_str(cluster.get("id") or cluster.get("cluster-uuid"))
    embedded = cluster.get("devices") or cluster.get("device-list") or []
    if isinstance(embedded, dict):
        embedded = [embedded]
    if not isinstance(embedded, list):
        return []

    devices: list[dict[str, Any]] = []
    for item in embedded:
        if not isinstance(item, dict):
            continue
        enriched = dict(item)
        if cluster_name and "cluster_name" not in enriched and "cluster-name" not in enriched:
            enriched["cluster-name"] = cluster_name
        if cluster_id and "cluster_id" not in enriched and "cluster-id" not in enriched:
            enriched["cluster-id"] = cluster_id
        devices.append(enriched)

    # Cluster itself can represent a single-node inventory row when no
    # embedded devices are present but the cluster has a usable name.
    if not devices and cluster_name:
        devices.append(
            {
                "device-id": cluster_id or cluster_name,
                "name": cluster_name,
                "hostname": cluster_name,
                "status": _optional_str(cluster.get("provision-state")),
                "cluster-name": cluster_name,
                "cluster-id": cluster_id,
                "device-count": cluster.get("device-count"),
            }
        )
    return devices


def _record_to_device(record: dict[str, Any]) -> A10Device | None:
    """Map one inventory API record to a normalized A10Device."""
    # Nested wrappers used by some controller payloads.
    value = record
    for nest in ("device", "result", "value", "data"):
        nested = value.get(nest) if isinstance(value, dict) else None
        if isinstance(nested, dict) and _looks_like_device(nested):
            value = nested
            break

    device_id = _first_str(
        value,
        "device-id",
        "device_id",
        "deviceId",
        "id",
        "uuid",
        "serial",
        "serial-number",
        "serial_number",
    )
    hostname = _first_str(
        value,
        "hostname",
        "host-name",
        "host_name",
        "device-name",
        "device_name",
        "name",
        "display-name",
        "display_name",
    )
    if not hostname:
        return None
    if not device_id:
        device_id = hostname

    return A10Device(
        device_id=device_id,
        hostname=hostname,
        model_name=_first_str(
            value,
            "model-name",
            "model_name",
            "modelName",
            "model",
            "product",
            "platform",
            "hardware",
        ),
        software_version=_first_str(
            value,
            "software-version",
            "software_version",
            "softwareVersion",
            "acos-version",
            "acos_version",
            "version",
        ),
        mgmt_ip=_first_str(
            value,
            "mgmt-ip",
            "mgmt_ip",
            "management-ip",
            "management_ip",
            "host",
            "ip-address",
            "ip_address",
            "ip",
        ),
        serial=_first_str(
            value,
            "serial",
            "serial-number",
            "serial_number",
            "serialNumber",
        ),
        status=_first_str(
            value,
            "status",
            "state",
            "connectivity-status",
            "connectivity_status",
            "provision-state",
            "provision_state",
            "health",
        ),
        cluster_name=_first_str(value, "cluster-name", "cluster_name", "clusterName"),
        cluster_id=_first_str(value, "cluster-id", "cluster_id", "clusterId"),
    )


def _looks_like_device(payload: dict[str, Any]) -> bool:
    """Heuristic: object has a name/hostname-like field."""
    return any(
        key in payload
        for key in (
            "hostname",
            "host-name",
            "device-name",
            "device_name",
            "name",
            "device-id",
            "device_id",
            "serial",
        )
    )


def _is_active(status: str | None) -> bool:
    """Return True when status is missing (assume active) or an active value."""
    if status is None or not status.strip():
        return True
    normalized = status.strip().lower().replace("_", "-").replace(" ", "-")
    if normalized in ACTIVE_STATUSES:
        return True
    # Common inactive markers
    if any(marker in normalized for marker in ("offline", "disconnect", "down", "fail", "inactive", "unknown")):
        return False
    # Unknown but non-empty status: keep when not clearly inactive.
    return True


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
