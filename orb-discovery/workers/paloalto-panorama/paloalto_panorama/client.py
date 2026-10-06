#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""Palo Alto Panorama XML API client (managed-device inventory)."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from typing import Protocol
from xml.etree.ElementTree import Element

import httpx

from paloalto_panorama.models import PanoramaDevice

logger = logging.getLogger(__name__)

API_PATH = "/api/"
SHOW_DEVICES_ALL = "<show><devices><all></all></devices></show>"

ACTIVE_STATUSES = frozenset(
    {
        "yes",
        "connected",
        "up",
        "active",
        "online",
    }
)


class InventoryClient(Protocol):
    """Fixture-friendly interface for listing Panorama managed devices."""

    def list_devices(self, *, active_only: bool = True) -> list[PanoramaDevice]:
        """Return managed-device inventory from Panorama."""
        ...


class PanoramaClient:
    """
    HTTP client for the Panorama XML operational API.

    Calls ``type=op`` with ``show devices all``, authenticating via the
    ``X-PAN-KEY`` header. Never log the API key.
    """

    def __init__(
        self,
        host: str,
        api_key: str,
        *,
        verify_ssl: bool = True,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """
        Construct the client.

        Args:
        ----
            host: Absolute Panorama base URL (no trailing slash).
            api_key: Panorama XML API key (never logged).
            verify_ssl: Whether to verify TLS certificates.
            timeout: Request timeout in seconds.
            transport: Optional httpx transport (used in tests).

        """
        self._host = host.rstrip("/")
        self._timeout = timeout
        self._client = httpx.Client(
            base_url=self._host,
            headers={
                "X-PAN-KEY": api_key,
                "Accept": "application/xml, text/xml, */*",
            },
            verify=verify_ssl,
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> PanoramaClient:
        """Enter context manager."""
        return self

    def __exit__(self, *args: object) -> None:
        """Exit context manager."""
        self.close()

    def list_devices(self, *, active_only: bool = True) -> list[PanoramaDevice]:
        """Fetch managed devices from Panorama via ``show devices all``."""
        response = self._client.post(
            API_PATH,
            data={
                "type": "op",
                "cmd": SHOW_DEVICES_ALL,
            },
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"Panorama devices request failed: HTTP {exc.response.status_code}") from exc

        try:
            root = ET.fromstring(response.text)
        except ET.ParseError as exc:
            raise RuntimeError("Panorama devices response was not valid XML") from exc

        status_attr = (root.get("status") or "").strip().lower()
        if status_attr and status_attr != "success":
            raise RuntimeError(f"Panorama devices request failed: status={status_attr}")

        devices: list[PanoramaDevice] = []
        for entry in root.findall(".//devices/entry"):
            device = _entry_to_device(entry)
            if device is None:
                continue
            if active_only and not _is_active(device.status):
                continue
            devices.append(device)

        logger.info(
            "Fetched %d Panorama device(s) from %s (active_only=%s)",
            len(devices),
            self._host,
            active_only,
        )
        return devices


def _entry_to_device(entry: Element) -> PanoramaDevice | None:
    """Map one ``<entry>`` element to a normalized PanoramaDevice."""
    serial = _child_text(entry, "serial") or (entry.get("name") or "").strip() or None
    hostname = _child_text(entry, "hostname") or _child_text(entry, "name") or serial
    if not hostname:
        return None
    device_id = serial or hostname

    return PanoramaDevice(
        device_id=device_id,
        hostname=hostname,
        model_name=_child_text(entry, "model"),
        software_version=_child_text(entry, "sw-version"),
        mgmt_ip=_child_text(entry, "ip-address") or _child_text(entry, "ipv6-address"),
        serial=serial,
        status=_child_text(entry, "connected") or _child_text(entry, "ha-state"),
        device_group=_child_text(entry, "device-group") or _child_text(entry, "dgname"),
        vsys=_child_text(entry, "vsys") or _child_text(entry, "multi-vsys"),
    )


def _child_text(element: Element, tag: str) -> str | None:
    """Return stripped text of the first child with the given tag."""
    child = element.find(tag)
    if child is None or child.text is None:
        return None
    text = child.text.strip()
    return text or None


def _is_active(status: str | None) -> bool:
    """Return True when status is missing (assume active) or an active value."""
    if status is None or not status.strip():
        return True
    normalized = status.strip().lower().replace("_", "-").replace(" ", "-")
    if normalized in ACTIVE_STATUSES:
        return True
    if any(marker in normalized for marker in ("no", "offline", "disconnect", "down", "fail", "inactive")):
        return False
    return True
