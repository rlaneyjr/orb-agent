#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""Tests for Panorama inventory mapping."""

from paloalto_panorama.map import map_device, map_devices
from paloalto_panorama.models import Defaults, PanoramaDevice


def _defaults(**overrides) -> Defaults:
    data = {
        "site": "dc1",
        "role": "firewall",
        "manufacturer": "Palo Alto Networks",
        "platform": "panos",
        "tags": ["panorama"],
    }
    data.update(overrides)
    return Defaults(**data)


def test_map_device_active():
    """Connected devices map to NetBox status active."""
    device = PanoramaDevice(
        device_id="007051000111111",
        hostname="fw-edge-01",
        model_name="PA-3220",
        software_version="10.2.3",
        mgmt_ip="10.40.1.11",
        serial="007051000111111",
        status="yes",
        device_group="edge-dg",
    )
    entity = map_device(device, _defaults())
    assert entity is not None
    assert entity.device.name == "fw-edge-01"
    assert entity.device.serial == "007051000111111"
    assert entity.device.status == "active"
    assert entity.device.device_type.model == "PA-3220"
    assert entity.device.device_type.manufacturer.name == "Palo Alto Networks"
    assert entity.device.site.name == "dc1"
    assert entity.device.role.name == "firewall"
    assert entity.device.platform.name == "panos"
    assert "PAN-OS 10.2.3" in entity.device.description
    assert "mgmt=10.40.1.11" in entity.device.description
    assert "device-group=edge-dg" in entity.device.description
    assert [t.name for t in entity.device.tags] == ["panorama"]


def test_map_device_inactive_status():
    """connected=no maps to offline."""
    device = PanoramaDevice(
        device_id="XYZ",
        hostname="fw-legacy",
        status="no",
    )
    entity = map_device(device, _defaults())
    assert entity is not None
    assert entity.device.status == "offline"
    assert entity.device.device_type.model == "unknown"
    assert entity.device.serial == "XYZ"


def test_map_device_skips_empty_hostname():
    """Devices without a hostname are skipped."""
    device = PanoramaDevice(device_id="XYZ", hostname="  ")
    assert map_device(device, _defaults()) is None


def test_map_devices_batch():
    """map_devices returns one entity per valid device."""
    devices = [
        PanoramaDevice(device_id="1", hostname="a", status="yes"),
        PanoramaDevice(device_id="2", hostname="b", status="yes"),
    ]
    entities = map_devices(devices, _defaults(tags=[]))
    assert len(entities) == 2
    assert entities[0].device.name == "a"
    assert entities[1].device.name == "b"
