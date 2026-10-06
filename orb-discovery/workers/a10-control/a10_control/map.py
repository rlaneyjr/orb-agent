#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""Map A10 Control inventory records to Diode entities."""

from __future__ import annotations

import logging
from collections.abc import Iterable

from netboxlabs.diode.sdk.ingester import Device, Entity

from a10_control.client import ACTIVE_STATUSES
from a10_control.models import A10Device, Defaults

logger = logging.getLogger(__name__)


def map_devices(devices: Iterable[A10Device], defaults: Defaults) -> list[Entity]:
    """Convert A10 Control devices into Diode Device entities."""
    entities: list[Entity] = []
    for device in devices:
        entity = map_device(device, defaults)
        if entity is not None:
            entities.append(entity)
    return entities


def map_device(device: A10Device, defaults: Defaults) -> Entity | None:
    """Map a single A10 Control device to a Diode Entity."""
    name = (device.hostname or "").strip()
    if not name:
        logger.warning("Skipping A10 Control device without hostname (id=%s)", device.device_id)
        return None

    status = _status_from_control(device.status)
    description_parts = []
    if device.software_version:
        description_parts.append(f"ACOS {device.software_version}")
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


def _status_from_control(status: str | None) -> str:
    """Map A10 Control status to a NetBox device status."""
    if status is None or not status.strip():
        return "active"
    normalized = status.strip().lower().replace("_", "-").replace(" ", "-")
    if normalized in ACTIVE_STATUSES:
        return "active"
    if any(marker in normalized for marker in ("offline", "disconnect", "down", "fail", "inactive")):
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
