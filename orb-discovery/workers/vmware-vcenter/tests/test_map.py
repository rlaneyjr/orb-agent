#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""Tests for vCenter inventory mapping."""

from vmware_vcenter.map import map_device, map_devices
from vmware_vcenter.models import Defaults, ESXiHost


def _defaults(**overrides) -> Defaults:
    data = {
        "site": "dc1",
        "role": "hypervisor",
        "manufacturer": "VMware",
        "platform": "esxi",
        "tags": ["vmware-vcenter"],
    }
    data.update(overrides)
    return Defaults(**data)


def test_map_device_active():
    """CONNECTED hosts map to NetBox status active."""
    device = ESXiHost(
        device_id="host-11",
        hostname="esxi-01.lab.example.com",
        status="CONNECTED",
        power_state="POWERED_ON",
        cluster_name="prod-cluster-a",
    )
    entity = map_device(device, _defaults())
    assert entity is not None
    assert entity.device.name == "esxi-01.lab.example.com"
    assert entity.device.serial == "host-11"
    assert entity.device.status == "active"
    assert entity.device.device_type.model == "unknown"
    assert entity.device.device_type.manufacturer.name == "VMware"
    assert entity.device.site.name == "dc1"
    assert entity.device.role.name == "hypervisor"
    assert entity.device.platform.name == "esxi"
    assert "power=POWERED_ON" in entity.device.description
    assert "cluster=prod-cluster-a" in entity.device.description
    assert [t.name for t in entity.device.tags] == ["vmware-vcenter"]


def test_map_device_inactive_status():
    """DISCONNECTED status maps to offline."""
    device = ESXiHost(
        device_id="host-33",
        hostname="esxi-legacy.lab.example.com",
        status="DISCONNECTED",
        power_state="POWERED_OFF",
    )
    entity = map_device(device, _defaults())
    assert entity is not None
    assert entity.device.status == "offline"
    assert entity.device.device_type.model == "unknown"
    assert entity.device.serial == "host-33"


def test_map_device_skips_empty_hostname():
    """Hosts without a hostname are skipped."""
    device = ESXiHost(device_id="host-99", hostname="  ")
    assert map_device(device, _defaults()) is None


def test_map_devices_batch():
    """map_devices returns one entity per valid host."""
    devices = [
        ESXiHost(device_id="1", hostname="a", status="CONNECTED"),
        ESXiHost(device_id="2", hostname="b", status="CONNECTED"),
    ]
    entities = map_devices(devices, _defaults(tags=[]))
    assert len(entities) == 2
    assert entities[0].device.name == "a"
    assert entities[1].device.name == "b"
