#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""Tests for Prism Central inventory mapping."""

from nutanix_pc.map import map_cluster, map_device, map_devices, map_inventory, map_vm
from nutanix_pc.models import ClusterInfo, Defaults, GuestVM, PCHost


def _defaults(**overrides) -> Defaults:
    data = {
        "site": "dc1",
        "role": "hypervisor",
        "manufacturer": "Nutanix",
        "platform": "ahv",
        "cluster_type": "Nutanix AHV",
        "vm_role": "vm",
        "vm_platform": "unknown",
        "tags": ["nutanix-pc"],
    }
    data.update(overrides)
    return Defaults(**data)


def test_map_cluster():
    """Clusters map to Diode Cluster with type and site."""
    entity = map_cluster(
        ClusterInfo(cluster_id="uuid-c1", name="prod-cluster-a", status="COMPLETE"),
        _defaults(),
    )
    assert entity is not None
    assert entity.WhichOneof("entity") == "cluster"
    assert entity.cluster.name == "prod-cluster-a"
    assert entity.cluster.type.name == "Nutanix AHV"
    assert entity.cluster.scope_site.name == "dc1"
    assert entity.cluster.status == "active"


def test_map_device_active():
    """Complete hosts map to NetBox status active and link to cluster."""
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
    assert entity.device.cluster.name == "prod-cluster-a"
    assert "Nutanix 20230302.100160" in entity.device.description
    assert "mgmt=10.20.1.11" in entity.device.description
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


def test_map_vm_active():
    """Powered-on VMs map to active VirtualMachine entities."""
    entity = map_vm(
        GuestVM(
            vm_id="vm-1",
            name="web-01",
            power_state="ON",
            cpu_count=4,
            memory_mib=8192,
            disk_gb=150,
            cluster_name="prod-cluster-a",
            host_name="NTNX-HOST-01",
            primary_ip="10.20.2.10",
        ),
        _defaults(),
    )
    assert entity is not None
    assert entity.WhichOneof("entity") == "virtual_machine"
    assert entity.virtual_machine.name == "web-01"
    assert entity.virtual_machine.status == "active"
    assert entity.virtual_machine.cluster.name == "prod-cluster-a"
    assert entity.virtual_machine.device.name == "NTNX-HOST-01"
    assert entity.virtual_machine.role.name == "vm"
    assert entity.virtual_machine.vcpus == 4.0
    assert entity.virtual_machine.memory == 8192
    assert entity.virtual_machine.disk == 150
    assert entity.virtual_machine.primary_ip4.address.startswith("10.20.2.10")


def test_map_vm_offline():
    """Powered-off VMs map to offline."""
    entity = map_vm(
        GuestVM(vm_id="vm-2", name="retired-app", power_state="OFF"),
        _defaults(),
    )
    assert entity is not None
    assert entity.virtual_machine.status == "offline"


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


def test_map_inventory_synthesizes_missing_clusters():
    """Clusters referenced by hosts are emitted even when not in the cluster list."""
    entities = map_inventory(
        [],
        [PCHost(device_id="1", hostname="a", status="COMPLETE", cluster_name="implied-cluster")],
        [],
        _defaults(tags=[]),
    )
    assert entities[0].WhichOneof("entity") == "cluster"
    assert entities[0].cluster.name == "implied-cluster"
    assert entities[1].device.cluster.name == "implied-cluster"
