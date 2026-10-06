#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""Nutanix Prism Central v3 hosts inventory client."""

from __future__ import annotations

import logging
from typing import Any, Protocol

import httpx

from nutanix_pc.models import PCHost

logger = logging.getLogger(__name__)

HOSTS_LIST_PATH = "/api/nutanix/v3/hosts/list"

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


class InventoryClient(Protocol):
    """Fixture-friendly interface for listing Prism Central hosts."""

    def list_devices(self, *, active_only: bool = True) -> list[PCHost]:
        """Return host inventory from Prism Central."""
        ...


class PrismCentralClient:
    """
    HTTP client for the Prism Central v3 hosts list API.

    Authenticates with HTTP Basic (Prism username/password). Never log the
    password. Endpoint: ``POST /api/nutanix/v3/hosts/list`` with body
    ``{"kind": "host"}``.
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

    def list_devices(self, *, active_only: bool = True) -> list[PCHost]:
        """Fetch physical hosts from Prism Central inventory."""
        response = self._client.post(HOSTS_LIST_PATH, json={"kind": "host"})
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # Do not include response body — it may echo auth material.
            raise RuntimeError(f"Prism Central hosts request failed: HTTP {exc.response.status_code}") from exc

        records = _parse_hosts_payload(response.json() if response.content else None)
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


def _parse_hosts_payload(payload: Any) -> list[dict[str, Any]]:
    """Parse Prism Central hosts/list responses."""
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
        cluster_name=_first_str(resources, "cluster_name", "cluster"),
        hypervisor=_first_str(resources, "hypervisor_type", "hypervisor_full_name")
        or _optional_str(hypervisor_info.get("type")),
    )


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
