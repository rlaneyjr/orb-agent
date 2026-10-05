#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""Map CloudVision inventory records to Diode entities."""

from __future__ import annotations

import logging
from collections.abc import Iterable

from netboxlabs.diode.sdk.ingester import Device, Entity

from arista_cv.models import CVDevice, Defaults

logger = logging.getLogger(__name__)

STREAMING_STATUS_ACTIVE = "STREAMING_STATUS_ACTIVE"


def map_devices(devices: Iterable[CVDevice], defaults: Defaults) -> list[Entity]:
    """Convert CloudVision devices into Diode Device entities."""
    entities: list[Entity] = []
    for device in devices:
        entity = map_device(device, defaults)
        if entity is not None:
            entities.append(entity)
    return entities


def map_device(device: CVDevice, defaults: Defaults) -> Entity | None:
    """Map a single CloudVision device to a Diode Entity."""
    name = (device.hostname or "").strip()
    if not name:
        logger.warning("Skipping CloudVision device without hostname (id=%s)", device.device_id)
        return None

    status = _status_from_streaming(device.streaming_status)
    description_parts = []
    if device.software_version:
        description_parts.append(f"EOS {device.software_version}")
    if device.fqdn and device.fqdn != name:
        description_parts.append(f"fqdn={device.fqdn}")
    if device.system_mac_address:
        description_parts.append(f"mac={device.system_mac_address}")

    diode_device = Device(
        name=name,
        device_type=device.model_name or "unknown",
        manufacturer=defaults.manufacturer,
        platform=defaults.platform,
        site=defaults.site,
        role=defaults.role,
        serial=device.device_id,
        status=status,
        description="; ".join(description_parts) if description_parts else None,
        tags=list(defaults.tags) if defaults.tags else None,
    )
    return Entity(device=diode_device)


def _status_from_streaming(streaming_status: str | None) -> str:
    """Map CloudVision streaming status to a NetBox device status."""
    if streaming_status == STREAMING_STATUS_ACTIVE:
        return "active"
    return "offline"
