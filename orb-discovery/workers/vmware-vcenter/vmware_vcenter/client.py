#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""VMware vCenter REST API ESXi host inventory client."""

from __future__ import annotations

import logging
from typing import Any, Protocol

import httpx

from vmware_vcenter.models import ESXiHost

logger = logging.getLogger(__name__)

SESSION_PATH = "/api/session"
HOSTS_PATH = "/api/vcenter/host"
SESSION_HEADER = "vmware-api-session-id"

# connection_state values treated as "active" when active_only=True.
ACTIVE_CONNECTION_STATES = frozenset({"connected"})


class InventoryClient(Protocol):
    """Fixture-friendly interface for listing vCenter ESXi hosts."""

    def list_devices(self, *, active_only: bool = True) -> list[ESXiHost]:
        """Return host inventory from vCenter."""
        ...


class VCenterClient:
    """
    HTTP client for the vSphere Automation REST host inventory API.

    Authenticates with ``POST /api/session`` (HTTP Basic) and sends the returned
    session id as ``vmware-api-session-id``. Never log the password or session id.
    Inventory: ``GET /api/vcenter/host``.
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

    def list_devices(self, *, active_only: bool = True) -> list[ESXiHost]:
        """Fetch ESXi hosts from vCenter inventory."""
        session_id = self._ensure_session()
        response = self._client.get(
            HOSTS_PATH,
            headers={SESSION_HEADER: session_id},
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # Do not include response body — it may echo auth material.
            raise RuntimeError(f"vCenter hosts request failed: HTTP {exc.response.status_code}") from exc

        records = _parse_hosts_payload(response.json() if response.content else None)
        devices: list[ESXiHost] = []
        for record in records:
            device = _record_to_host(record)
            if device is None:
                continue
            if active_only and not _is_active(device.status):
                continue
            devices.append(device)

        logger.info(
            "Fetched %d vCenter host(s) from %s (active_only=%s)",
            len(devices),
            self._host,
            active_only,
        )
        return devices

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


def _parse_hosts_payload(payload: Any) -> list[dict[str, Any]]:
    """Parse GET /api/vcenter/host responses (list or wrapped)."""
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


def _is_active(status: str | None) -> bool:
    """Return True when connection_state is missing (assume active) or CONNECTED."""
    if status is None or not status.strip():
        return True
    normalized = status.strip().lower().replace("_", "-").replace(" ", "-")
    if normalized in ACTIVE_CONNECTION_STATES:
        return True
    if any(marker in normalized for marker in ("disconnect", "not-responding", "offline", "down")):
        return False
    return True


def _optional_str(value: Any) -> str | None:
    """Coerce a non-empty value to str, else None."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None
