#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""Tests for VMwareVCenterBackend policy handling."""

from unittest.mock import MagicMock

import pytest
from worker.backend import load_class
from worker.models import Config, Policy

from vmware_vcenter.backend import APP_NAME, APP_VERSION, VMwareVCenterBackend
from vmware_vcenter.models import ClusterInfo, ESXiHost, GuestVM


def _policy(**overrides) -> Policy:
    data = {
        "config": {
            "package": "vmware_vcenter",
            "defaults": {
                "site": "dc1",
                "role": "hypervisor",
                "manufacturer": "VMware",
                "platform": "esxi",
                "tags": ["vmware"],
            },
        },
        "scope": {
            "host": "https://vcenter.example.com",
            "username": "admin@vsphere.local",
            "password": "test-password",
        },
    }
    data.update(overrides)
    return Policy(config=Config(**data["config"]), scope=data["scope"])


def test_describe():
    """describe returns stable metadata."""
    meta = VMwareVCenterBackend.describe()
    assert meta.name == "vmware_vcenter"
    assert meta.app_name == APP_NAME
    assert meta.app_version == APP_VERSION


def test_load_class_discovers_backend():
    """Worker load_class finds VMwareVCenterBackend via package import."""
    assert load_class("vmware_vcenter") is VMwareVCenterBackend


def test_run_maps_inventory_from_client():
    """run() uses the injected client and maps clusters/hosts/VMs to entities."""
    mock_client = MagicMock()
    mock_client.list_clusters.return_value = [
        ClusterInfo(cluster_id="domain-c21", name="prod-cluster-a", ha_enabled=True, drs_enabled=True)
    ]
    mock_client.list_devices.return_value = [
        ESXiHost(
            device_id="host-11",
            hostname="esxi-01.lab.example.com",
            status="CONNECTED",
            power_state="POWERED_ON",
            cluster_name="prod-cluster-a",
        )
    ]
    mock_client.list_vms.return_value = [
        GuestVM(
            vm_id="vm-101",
            name="web-01",
            power_state="POWERED_ON",
            cpu_count=4,
            memory_mib=8192,
            cluster_name="prod-cluster-a",
            host_name="esxi-01.lab.example.com",
        )
    ]

    backend = VMwareVCenterBackend(client_factory=lambda scope, config: mock_client)
    entities = list(backend.run("vmware_vcenter_inventory", _policy()))

    mock_client.list_clusters.assert_called_once_with()
    mock_client.list_devices.assert_called_once_with(active_only=True)
    mock_client.list_vms.assert_called_once_with(active_only=True)
    mock_client.close.assert_called_once()
    assert len(entities) == 3
    assert entities[0].WhichOneof("entity") == "cluster"
    assert entities[0].cluster.name == "prod-cluster-a"
    assert entities[1].device.name == "esxi-01.lab.example.com"
    assert entities[1].device.cluster.name == "prod-cluster-a"
    assert entities[2].virtual_machine.name == "web-01"
    assert entities[2].virtual_machine.device.name == "esxi-01.lab.example.com"


def test_run_rejects_bad_package():
    """Wrong config.package fails validation."""
    backend = VMwareVCenterBackend(client_factory=lambda *_: MagicMock())
    policy = _policy(
        config={
            "package": "other",
            "defaults": {"site": "dc1"},
        }
    )
    with pytest.raises(ValueError, match="Invalid vmware_vcenter policy"):
        list(backend.run("bad", policy))


def test_run_rejects_non_mapping_scope():
    """Scope must be a mapping."""
    backend = VMwareVCenterBackend(client_factory=lambda *_: MagicMock())
    policy = Policy(
        config=Config.model_validate(
            {
                "package": "vmware_vcenter",
                "defaults": {"site": "dc1"},
            }
        ),
        scope=["not", "a", "map"],
    )
    with pytest.raises(ValueError, match="scope must be a mapping"):
        list(backend.run("bad", policy))


def test_run_rejects_missing_password():
    """Missing password fails scope validation."""
    backend = VMwareVCenterBackend(client_factory=lambda *_: MagicMock())
    policy = _policy(scope={"host": "https://vcenter.example.com", "username": "admin"})
    with pytest.raises(ValueError, match="Invalid vmware_vcenter policy"):
        list(backend.run("bad", policy))


def test_run_rejects_relative_host():
    """Host must be an absolute URL."""
    backend = VMwareVCenterBackend(client_factory=lambda *_: MagicMock())
    policy = _policy(
        scope={"host": "vcenter.example.com", "username": "admin", "password": "pw"}
    )
    with pytest.raises(ValueError, match="Invalid vmware_vcenter policy"):
        list(backend.run("bad", policy))
