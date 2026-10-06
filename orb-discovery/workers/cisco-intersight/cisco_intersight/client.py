#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""Cisco Intersight API client (HTTP signature auth + compute inventory)."""

from __future__ import annotations

import hashlib
import logging
from base64 import b64encode
from email.utils import formatdate
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from cisco_intersight.models import IntersightDevice

logger = logging.getLogger(__name__)

PHYSICAL_SUMMARIES_PATH = "/api/v1/compute/PhysicalSummaries"

# Power / reachability values treated as active when active_only=True.
ACTIVE_STATUSES = frozenset(
    {
        "on",
        "powered-on",
        "poweredon",
        "active",
        "online",
        "ok",
        "connected",
        "reachable",
    }
)


class InventoryClient(Protocol):
    """Fixture-friendly interface for listing Intersight devices."""

    def list_devices(self, *, active_only: bool = True) -> list[IntersightDevice]:
        """Return compute inventory from Intersight."""
        ...


class IntersightClient:
    """
    HTTP client for Cisco Intersight compute inventory.

    Authenticates each request with an RSA-SHA256 HTTP signature using the
    API key ID and PEM secret key. Never log the secret key.
    """

    def __init__(
        self,
        host: str,
        api_key_id: str,
        secret_key: str,
        *,
        verify_ssl: bool = True,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """
        Construct the client.

        Args:
        ----
            host: Absolute Intersight base URL (no trailing slash).
            api_key_id: Intersight API key ID.
            secret_key: PEM-encoded RSA private key contents.
            verify_ssl: Whether to verify TLS certificates.
            timeout: Request timeout in seconds.
            transport: Optional httpx transport (used in tests).

        """
        self._host = host.rstrip("/")
        self._api_key_id = api_key_id
        self._private_key = serialization.load_pem_private_key(
            secret_key.encode("utf-8"),
            password=None,
        )
        self._timeout = timeout
        parsed = urlparse(self._host)
        self._hostname = parsed.hostname or "intersight.com"
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
        """Close the underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> IntersightClient:
        """Enter context manager."""
        return self

    def __exit__(self, *args: object) -> None:
        """Exit context manager."""
        self.close()

    def list_devices(self, *, active_only: bool = True) -> list[IntersightDevice]:
        """Fetch compute physical summaries from Intersight."""
        path = PHYSICAL_SUMMARIES_PATH
        headers = self._signed_headers("GET", path, body=b"")
        response = self._client.get(path, headers=headers)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"Intersight inventory request failed: HTTP {exc.response.status_code}") from exc

        records = _parse_results_payload(response.json() if response.content else None)
        devices: list[IntersightDevice] = []
        for record in records:
            device = _record_to_device(record)
            if device is None:
                continue
            if active_only and not _is_active(device.status):
                continue
            devices.append(device)

        logger.info(
            "Fetched %d Intersight device(s) from %s (active_only=%s)",
            len(devices),
            self._host,
            active_only,
        )
        return devices

    def _signed_headers(self, method: str, path: str, *, body: bytes) -> dict[str, str]:
        """Build Intersight HTTP signature headers for one request."""
        date = formatdate(timeval=None, localtime=False, usegmt=True)
        digest = "SHA-256=" + b64encode(hashlib.sha256(body).digest()).decode("ascii")
        request_target = f"{method.lower()} {path}"
        string_to_sign = "\n".join(
            [
                f"(request-target): {request_target}",
                f"date: {date}",
                f"host: {self._hostname}",
                f"digest: {digest}",
            ]
        )
        signature = b64encode(
            self._private_key.sign(
                string_to_sign.encode("utf-8"),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
        ).decode("ascii")
        authorization = (
            f'Signature keyId="{self._api_key_id}",'
            f'algorithm="rsa-sha256",'
            f'headers="(request-target) date host digest",'
            f'signature="{signature}"'
        )
        return {
            "Date": date,
            "Host": self._hostname,
            "Digest": digest,
            "Authorization": authorization,
        }


def _parse_results_payload(payload: Any) -> list[dict[str, Any]]:
    """Parse Intersight list responses (Results / results / bare list)."""
    if payload is None:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("Results", "results", "items", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _record_to_device(record: dict[str, Any]) -> IntersightDevice | None:
    """Map one PhysicalSummary object to a normalized IntersightDevice."""
    device_id = _first_str(record, "Moid", "moid", "ObjectType", "DeviceMoId", "Uuid", "uuid")
    hostname = _first_str(record, "Name", "name", "Dn", "dn", "AssetTag", "assetTag")
    if not hostname:
        return None
    if not device_id:
        device_id = hostname

    return IntersightDevice(
        device_id=device_id,
        hostname=hostname,
        model_name=_first_str(record, "Model", "model", "PlatformType", "platformType"),
        software_version=_first_str(record, "Firmware", "firmware", "FirmwareVersion", "firmwareVersion"),
        mgmt_ip=_first_str(
            record,
            "MgmtIpAddress",
            "mgmtIpAddress",
            "ManagementIpAddress",
            "managementIpAddress",
            "Ipv4Address",
            "ipv4Address",
        ),
        serial=_first_str(record, "Serial", "serial", "SerialNumber", "serialNumber"),
        status=_first_str(
            record,
            "OperPowerState",
            "operPowerState",
            "AdminPowerState",
            "adminPowerState",
            "ConnectionStatus",
            "connectionStatus",
            "Presence",
            "presence",
        ),
        vendor=_first_str(record, "Vendor", "vendor", "Manufacturer", "manufacturer"),
    )


def _is_active(status: str | None) -> bool:
    """Return True when status is missing (assume active) or an active value."""
    if status is None or not status.strip():
        return True
    normalized = status.strip().lower().replace("_", "-").replace(" ", "-")
    if normalized in ACTIVE_STATUSES:
        return True
    if any(marker in normalized for marker in ("off", "offline", "disconnect", "down", "fail", "absent", "unclaimed")):
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
