#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""Tests for vCenter inventory mapping."""

from vmware_vcenter.map import map_cluster, map_device, map_devices, map_inventory, map_vm
from vmware_vcenter.models import ClusterInfo, Defaults, ESXiHost, GuestVM


def _defaults(**overrides) -> Defaults:
    data = {
        "site": "dc1",
        "role": "hypervisor",
        "manufacturer": "VMware",
        "platform": "esxi",
        "cluster_type": "VMware vSphere",
        "vm_role": "vm",
        "vm_platform": "unknown",
        "tags": ["vmware-vcenter"],
    }
    data.update(overrides)
    return Defaults(**data)


def test_map_cluster():
    """Clusters map to Diode Cluster with type and site."""
    entity = map_cluster(
        ClusterInfo(cluster_id="domain-c21", name="prod-cluster-a", ha_enabled=True, drs_enabled=False),
        _defaults(),
    )
    assert entity is not None
    assert entity.WhichOneof("entity") == "cluster"
    assert entity.cluster.name == "prod-cluster-a"
    assert entity.cluster.type.name == "VMware vSphere"
    assert entity.cluster.scope_site.name == "dc1"
    assert "ha=True" in entity.cluster.description
    assert "drs=False" in entity.cluster.description


def test_map_device_active():
    """CONNECTED hosts map to NetBox status active and link to cluster."""
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
    assert entity.device.cluster.name == "prod-cluster-a"
    assert "power=POWERED_ON" in entity.device.description
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


def test_map_vm_active():
    """POWERED_ON VMs map to active VirtualMachine entities."""
    entity = map_vm(
        GuestVM(
            vm_id="vm-101",
            name="web-01",
            power_state="POWERED_ON",
            cpu_count=4,
            memory_mib=8192,
            cluster_name="prod-cluster-a",
            host_name="esxi-01.lab.example.com",
        ),
        _defaults(),
    )
    assert entity is not None
    assert entity.WhichOneof("entity") == "virtual_machine"
    assert entity.virtual_machine.name == "web-01"
    assert entity.virtual_machine.status == "active"
    assert entity.virtual_machine.cluster.name == "prod-cluster-a"
    assert entity.virtual_machine.device.name == "esxi-01.lab.example.com"
    assert entity.virtual_machine.role.name == "vm"
    assert entity.virtual_machine.platform.name == "unknown"
    assert entity.virtual_machine.vcpus == 4.0
    assert entity.virtual_machine.memory == 8192


def test_map_vm_offline():
    """POWERED_OFF VMs map to offline."""
    entity = map_vm(
        GuestVM(vm_id="vm-199", name="retired-app", power_state="POWERED_OFF"),
        _defaults(),
    )
    assert entity is not None
    assert entity.virtual_machine.status == "offline"


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


def test_map_inventory_order():
    """map_inventory emits clusters, then devices, then VMs."""
    entities = map_inventory(
        [ClusterInfo(cluster_id="c1", name="prod-cluster-a")],
        [ESXiHost(device_id="h1", hostname="esxi-01", cluster_name="prod-cluster-a", status="CONNECTED")],
        [
            GuestVM(
                vm_id="vm-1",
                name="web-01",
                power_state="POWERED_ON",
                cluster_name="prod-cluster-a",
                host_name="esxi-01",
            )
        ],
        _defaults(tags=[]),
    )
    assert [e.WhichOneof("entity") for e in entities] == ["cluster", "device", "virtual_machine"]
