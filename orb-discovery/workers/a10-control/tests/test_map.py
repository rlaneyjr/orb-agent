#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""Tests for A10 Control inventory mapping."""

from a10_control.map import map_device, map_devices
from a10_control.models import A10Device, Defaults


def _defaults(**overrides) -> Defaults:
    data = {
        "site": "dc1",
        "role": "load-balancer",
        "manufacturer": "A10 Networks",
        "platform": "acos",
        "tags": ["a10-control"],
    }
    data.update(overrides)
    return Defaults(**data)


def test_map_device_active():
    """Connected devices map to NetBox status active."""
    device = A10Device(
        device_id="uuid-1",
        hostname="thunder-adc-01",
        model_name="Thunder 1040S",
        software_version="5.2.1-P6",
        mgmt_ip="10.10.1.11",
        serial="AX12345678",
        status="connected",
        cluster_name="adc-cluster-a",
    )
    entity = map_device(device, _defaults())
    assert entity is not None
    assert entity.device.name == "thunder-adc-01"
    assert entity.device.serial == "AX12345678"
    assert entity.device.status == "active"
    assert entity.device.device_type.model == "Thunder 1040S"
    assert entity.device.device_type.manufacturer.name == "A10 Networks"
    assert entity.device.site.name == "dc1"
    assert entity.device.role.name == "load-balancer"
    assert entity.device.platform.name == "acos"
    assert "ACOS 5.2.1-P6" in entity.device.description
    assert "mgmt=10.10.1.11" in entity.device.description
    assert "cluster=adc-cluster-a" in entity.device.description
    assert [t.name for t in entity.device.tags] == ["a10-control"]


def test_map_device_inactive_status():
    """Disconnected status maps to offline."""
    device = A10Device(
        device_id="XYZ",
        hostname="thunder-legacy",
        status="disconnected",
    )
    entity = map_device(device, _defaults())
    assert entity is not None
    assert entity.device.status == "offline"
    assert entity.device.device_type.model == "unknown"
    assert entity.device.serial == "XYZ"


def test_map_device_skips_empty_hostname():
    """Devices without a hostname are skipped."""
    device = A10Device(device_id="XYZ", hostname="  ")
    assert map_device(device, _defaults()) is None


def test_map_devices_batch():
    """map_devices returns one entity per valid device."""
    devices = [
        A10Device(device_id="1", hostname="a", status="connected"),
        A10Device(device_id="2", hostname="b", status="connected"),
    ]
    entities = map_devices(devices, _defaults(tags=[]))
    assert len(entities) == 2
    assert entities[0].device.name == "a"
    assert entities[1].device.name == "b"
