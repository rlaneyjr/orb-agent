#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""CloudVision Resource API client (CVaaS and on-prem CVP)."""

from __future__ import annotations

import json
import logging
from json import JSONDecodeError, JSONDecoder
from typing import Any, Protocol

import httpx

from arista_cv.models import CVDevice

logger = logging.getLogger(__name__)

DEVICES_PATH = "/api/resources/inventory/v1/Device/all"
STREAMING_STATUS_ACTIVE = "STREAMING_STATUS_ACTIVE"


class InventoryClient(Protocol):
    """Fixture-friendly interface for listing CloudVision devices."""

    def list_devices(self, *, active_only: bool = True) -> list[CVDevice]:
        """Return inventory devices from CloudVision."""
        ...


class CloudVisionClient:
    """
    HTTP client for the CloudVision Inventory Resource API.

    Works against CVaaS (e.g. https://www.arista.io) and on-prem CVP using a
    service-account token as ``Authorization: Bearer <token>``.
    """

    def __init__(
        self,
        host: str,
        token: str,
        *,
        verify_ssl: bool = True,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """
        Construct the client.

        Args:
        ----
            host: Absolute CloudVision base URL (no trailing slash).
            token: Service account token (never logged).
            verify_ssl: Whether to verify TLS certificates.
            timeout: Request timeout in seconds.
            transport: Optional httpx transport (used in tests).

        """
        self._host = host.rstrip("/")
        self._timeout = timeout
        self._client = httpx.Client(
            base_url=self._host,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            verify=verify_ssl,
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> CloudVisionClient:
        """Enter context manager."""
        return self

    def __exit__(self, *args: object) -> None:
        """Exit context manager."""
        self.close()

    def list_devices(self, *, active_only: bool = True) -> list[CVDevice]:
        """
        Fetch devices from ``GET /api/resources/inventory/v1/Device/all``.

        The Resource API returns concatenated JSON objects (NDJSON-like). Some
        gateways wrap the stream as ``{"data": [...]}``; both shapes are accepted.
        """
        response = self._client.get(DEVICES_PATH)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # Do not include response body — it may echo auth material.
            raise RuntimeError(
                f"CloudVision inventory request failed: HTTP {exc.response.status_code}"
            ) from exc

        records = _parse_inventory_payload(response.text)
        devices: list[CVDevice] = []
        for record in records:
            device = _record_to_device(record)
            if device is None:
                continue
            if active_only and device.streaming_status != STREAMING_STATUS_ACTIVE:
                continue
            devices.append(device)

        logger.info(
            "Fetched %d CloudVision device(s) from %s (active_only=%s)",
            len(devices),
            self._host,
            active_only,
        )
        return devices


def _parse_inventory_payload(text: str) -> list[dict[str, Any]]:
    """Parse NDJSON or ``{"data": [...]}`` inventory responses."""
    stripped = text.strip()
    if not stripped:
        return []

    try:
        parsed = json.loads(stripped)
    except JSONDecodeError:
        return _decode_concatenated_json(stripped)

    if isinstance(parsed, dict) and isinstance(parsed.get("data"), list):
        return [item for item in parsed["data"] if isinstance(item, dict)]
    if isinstance(parsed, dict):
        return [parsed]
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    return []


def _decode_concatenated_json(data: str) -> list[dict[str, Any]]:
    """Decode back-to-back JSON objects as returned by Device/all."""
    decoder = JSONDecoder()
    pos = 0
    length = len(data)
    result: list[dict[str, Any]] = []
    while pos < length:
        while pos < length and data[pos].isspace():
            pos += 1
        if pos >= length:
            break
        try:
            obj, end = decoder.raw_decode(data, pos)
        except JSONDecodeError:
            break
        if isinstance(obj, dict):
            result.append(obj)
        pos = end
    return result


def _record_to_device(record: dict[str, Any]) -> CVDevice | None:
    """Map one inventory API record to a normalized CVDevice."""
    value = record.get("result", {}).get("value") if "result" in record else record.get("value")
    if not isinstance(value, dict):
        # Some responses nest key under value; skip malformed rows.
        return None

    key = value.get("key") or {}
    device_id = key.get("deviceId") or key.get("device_id")
    hostname = value.get("hostname") or value.get("fqdn")
    if not device_id or not hostname:
        return None

    return CVDevice(
        device_id=str(device_id),
        hostname=str(hostname),
        model_name=_optional_str(value.get("modelName") or value.get("model_name")),
        software_version=_optional_str(
            value.get("softwareVersion") or value.get("software_version")
        ),
        fqdn=_optional_str(value.get("fqdn")),
        system_mac_address=_optional_str(
            value.get("systemMacAddress") or value.get("system_mac_address")
        ),
        streaming_status=_optional_str(
            value.get("streamingStatus") or value.get("streaming_status")
        ),
        hardware_revision=_optional_str(
            value.get("hardwareRevision") or value.get("hardware_revision")
        ),
        domain_name=_optional_str(value.get("domainName") or value.get("domain_name")),
    )


def _optional_str(value: Any) -> str | None:
    """Coerce a non-empty value to str, else None."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None
