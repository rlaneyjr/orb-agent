#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""Tests for Intersight inventory mapping."""

from cisco_intersight.map import map_device, map_devices
from cisco_intersight.models import Defaults, IntersightDevice


def _defaults(**overrides) -> Defaults:
    data = {
        "site": "dc1",
        "role": "server",
        "manufacturer": "Cisco",
        "platform": "ucs",
        "tags": ["intersight"],
    }
    data.update(overrides)
    return Defaults(**data)


def test_map_device_active():
    """Powered-on devices map to NetBox status active."""
    device = IntersightDevice(
        device_id="moid-1",
        hostname="ucs-c220-01",
        model_name="UCSC-C220-M5SX",
        software_version="4.2(1a)",
        mgmt_ip="10.30.1.11",
        serial="FCH1234567A",
        status="on",
        vendor="Cisco Systems Inc",
    )
    entity = map_device(device, _defaults())
    assert entity is not None
    assert entity.device.name == "ucs-c220-01"
    assert entity.device.serial == "FCH1234567A"
    assert entity.device.status == "active"
    assert entity.device.device_type.model == "UCSC-C220-M5SX"
    assert entity.device.device_type.manufacturer.name == "Cisco"
    assert entity.device.site.name == "dc1"
    assert entity.device.role.name == "server"
    assert entity.device.platform.name == "ucs"
    assert "firmware 4.2(1a)" in entity.device.description
    assert "mgmt=10.30.1.11" in entity.device.description
    assert [t.name for t in entity.device.tags] == ["intersight"]


def test_map_device_inactive_status():
    """Powered-off status maps to offline."""
    device = IntersightDevice(
        device_id="XYZ",
        hostname="ucs-legacy",
        status="off",
    )
    entity = map_device(device, _defaults())
    assert entity is not None
    assert entity.device.status == "offline"
    assert entity.device.device_type.model == "unknown"
    assert entity.device.serial == "XYZ"


def test_map_device_skips_empty_hostname():
    """Devices without a hostname are skipped."""
    device = IntersightDevice(device_id="XYZ", hostname="  ")
    assert map_device(device, _defaults()) is None


def test_map_devices_batch():
    """map_devices returns one entity per valid device."""
    devices = [
        IntersightDevice(device_id="1", hostname="a", status="on"),
        IntersightDevice(device_id="2", hostname="b", status="on"),
    ]
    entities = map_devices(devices, _defaults(tags=[]))
    assert len(entities) == 2
    assert entities[0].device.name == "a"
    assert entities[1].device.name == "b"
