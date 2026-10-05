#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""Tests for CloudVision inventory mapping."""

from arista_cv.map import map_device, map_devices
from arista_cv.models import CVDevice, Defaults


def _defaults(**overrides) -> Defaults:
    data = {
        "site": "dc1",
        "role": "leaf",
        "manufacturer": "Arista",
        "platform": "eos",
        "tags": ["cloudvision"],
    }
    data.update(overrides)
    return Defaults(**data)


def test_map_device_active():
    """Active streaming devices map to NetBox status active."""
    device = CVDevice(
        device_id="ABC123",
        hostname="leaf1",
        model_name="vEOS-lab",
        software_version="4.27.0F",
        fqdn="leaf1.lab",
        system_mac_address="50:08:00:a7:ca:c3",
        streaming_status="STREAMING_STATUS_ACTIVE",
    )
    entity = map_device(device, _defaults())
    assert entity is not None
    assert entity.device.name == "leaf1"
    assert entity.device.serial == "ABC123"
    assert entity.device.status == "active"
    assert entity.device.device_type.model == "vEOS-lab"
    assert entity.device.device_type.manufacturer.name == "Arista"
    assert entity.device.site.name == "dc1"
    assert entity.device.role.name == "leaf"
    assert entity.device.platform.name == "eos"
    assert "EOS 4.27.0F" in entity.device.description
    assert "mac=50:08:00:a7:ca:c3" in entity.device.description
    assert [t.name for t in entity.device.tags] == ["cloudvision"]


def test_map_device_inactive_status():
    """Inactive streaming maps to offline."""
    device = CVDevice(
        device_id="XYZ",
        hostname="spine1",
        streaming_status="STREAMING_STATUS_INACTIVE",
    )
    entity = map_device(device, _defaults())
    assert entity is not None
    assert entity.device.status == "offline"
    assert entity.device.device_type.model == "unknown"


def test_map_device_skips_empty_hostname():
    """Devices without a hostname are skipped."""
    device = CVDevice(device_id="XYZ", hostname="  ")
    assert map_device(device, _defaults()) is None


def test_map_devices_batch():
    """map_devices returns one entity per valid device."""
    devices = [
        CVDevice(device_id="1", hostname="a", streaming_status="STREAMING_STATUS_ACTIVE"),
        CVDevice(device_id="2", hostname="b", streaming_status="STREAMING_STATUS_ACTIVE"),
    ]
    entities = map_devices(devices, _defaults(tags=[]))
    assert len(entities) == 2
    assert entities[0].device.name == "a"
    assert entities[1].device.name == "b"
