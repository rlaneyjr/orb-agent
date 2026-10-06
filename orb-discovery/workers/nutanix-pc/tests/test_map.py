#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""Tests for Prism Central inventory mapping."""

from nutanix_pc.map import map_device, map_devices
from nutanix_pc.models import Defaults, PCHost


def _defaults(**overrides) -> Defaults:
    data = {
        "site": "dc1",
        "role": "hypervisor",
        "manufacturer": "Nutanix",
        "platform": "ahv",
        "tags": ["nutanix-pc"],
    }
    data.update(overrides)
    return Defaults(**data)


def test_map_device_active():
    """Complete hosts map to NetBox status active."""
    device = PCHost(
        device_id="uuid-1",
        hostname="NTNX-HOST-01",
        model_name="NX-1065-G7",
        software_version="Nutanix 20230302.100160",
        mgmt_ip="10.20.1.11",
        serial="19SM6H230123",
        status="COMPLETE",
        cluster_name="prod-cluster-a",
        hypervisor="AHV",
    )
    entity = map_device(device, _defaults())
    assert entity is not None
    assert entity.device.name == "NTNX-HOST-01"
    assert entity.device.serial == "19SM6H230123"
    assert entity.device.status == "active"
    assert entity.device.device_type.model == "NX-1065-G7"
    assert entity.device.device_type.manufacturer.name == "Nutanix"
    assert entity.device.site.name == "dc1"
    assert entity.device.role.name == "hypervisor"
    assert entity.device.platform.name == "ahv"
    assert "Nutanix 20230302.100160" in entity.device.description
    assert "mgmt=10.20.1.11" in entity.device.description
    assert "cluster=prod-cluster-a" in entity.device.description
    assert [t.name for t in entity.device.tags] == ["nutanix-pc"]


def test_map_device_inactive_status():
    """Error status maps to offline."""
    device = PCHost(
        device_id="XYZ",
        hostname="NTNX-HOST-LEGACY",
        status="ERROR",
    )
    entity = map_device(device, _defaults())
    assert entity is not None
    assert entity.device.status == "offline"
    assert entity.device.device_type.model == "unknown"
    assert entity.device.serial == "XYZ"


def test_map_device_skips_empty_hostname():
    """Hosts without a hostname are skipped."""
    device = PCHost(device_id="XYZ", hostname="  ")
    assert map_device(device, _defaults()) is None


def test_map_devices_batch():
    """map_devices returns one entity per valid host."""
    devices = [
        PCHost(device_id="1", hostname="a", status="COMPLETE"),
        PCHost(device_id="2", hostname="b", status="COMPLETE"),
    ]
    entities = map_devices(devices, _defaults(tags=[]))
    assert len(entities) == 2
    assert entities[0].device.name == "a"
    assert entities[1].device.name == "b"
