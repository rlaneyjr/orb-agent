#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""Tests for NutanixPCBackend policy handling."""

from unittest.mock import MagicMock

import pytest
from worker.backend import load_class
from worker.models import Config, Policy

from nutanix_pc.backend import APP_NAME, APP_VERSION, NutanixPCBackend
from nutanix_pc.models import ClusterInfo, GuestVM, PCHost


def _policy(**overrides) -> Policy:
    data = {
        "config": {
            "package": "nutanix_pc",
            "defaults": {
                "site": "dc1",
                "role": "hypervisor",
                "manufacturer": "Nutanix",
                "platform": "ahv",
                "tags": ["nutanix"],
            },
        },
        "scope": {
            "host": "https://pc.example.com:9440",
            "username": "admin",
            "password": "test-password",
        },
    }
    data.update(overrides)
    return Policy(config=Config(**data["config"]), scope=data["scope"])


def test_describe():
    """describe returns stable metadata."""
    meta = NutanixPCBackend.describe()
    assert meta.name == "nutanix_pc"
    assert meta.app_name == APP_NAME
    assert meta.app_version == APP_VERSION


def test_load_class_discovers_backend():
    """Worker load_class finds NutanixPCBackend via package import."""
    assert load_class("nutanix_pc") is NutanixPCBackend


def test_run_maps_inventory_from_client():
    """run() uses the injected client and maps clusters/hosts/VMs to entities."""
    mock_client = MagicMock()
    mock_client.list_clusters.return_value = [
        ClusterInfo(cluster_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", name="prod-cluster-a", status="COMPLETE")
    ]
    mock_client.list_devices.return_value = [
        PCHost(
            device_id="11111111-2222-3333-4444-555555555555",
            hostname="NTNX-HOST-01",
            model_name="NX-1065-G7",
            software_version="Nutanix 20230302.100160",
            mgmt_ip="10.20.1.11",
            serial="19SM6H230123",
            status="COMPLETE",
            cluster_name="prod-cluster-a",
        )
    ]
    mock_client.list_vms.return_value = [
        GuestVM(
            vm_id="vm-aaaa-1111-2222-3333-444444444444",
            name="web-01",
            power_state="ON",
            cpu_count=4,
            memory_mib=8192,
            disk_gb=150,
            cluster_name="prod-cluster-a",
            host_name="NTNX-HOST-01",
            primary_ip="10.20.2.10",
        )
    ]

    backend = NutanixPCBackend(client_factory=lambda scope, config: mock_client)
    entities = list(backend.run("nutanix_pc_inventory", _policy()))

    mock_client.list_clusters.assert_called_once_with()
    mock_client.list_devices.assert_called_once_with(active_only=True)
    mock_client.list_vms.assert_called_once_with(active_only=True)
    mock_client.close.assert_called_once()
    assert len(entities) == 3
    assert entities[0].WhichOneof("entity") == "cluster"
    assert entities[0].cluster.name == "prod-cluster-a"
    assert entities[1].device.name == "NTNX-HOST-01"
    assert entities[1].device.cluster.name == "prod-cluster-a"
    assert entities[2].virtual_machine.name == "web-01"
    assert entities[2].virtual_machine.device.name == "NTNX-HOST-01"


def test_run_rejects_bad_package():
    """Wrong config.package fails validation."""
    backend = NutanixPCBackend(client_factory=lambda *_: MagicMock())
    policy = _policy(
        config={
            "package": "other",
            "defaults": {"site": "dc1"},
        }
    )
    with pytest.raises(ValueError, match="Invalid nutanix_pc policy"):
        list(backend.run("bad", policy))


def test_run_rejects_non_mapping_scope():
    """Scope must be a mapping."""
    backend = NutanixPCBackend(client_factory=lambda *_: MagicMock())
    policy = Policy(
        config=Config.model_validate(
            {
                "package": "nutanix_pc",
                "defaults": {"site": "dc1"},
            }
        ),
        scope=["not", "a", "map"],
    )
    with pytest.raises(ValueError, match="scope must be a mapping"):
        list(backend.run("bad", policy))


def test_run_rejects_missing_password():
    """Missing password fails scope validation."""
    backend = NutanixPCBackend(client_factory=lambda *_: MagicMock())
    policy = _policy(scope={"host": "https://pc.example.com:9440", "username": "admin"})
    with pytest.raises(ValueError, match="Invalid nutanix_pc policy"):
        list(backend.run("bad", policy))


def test_run_rejects_relative_host():
    """Host must be an absolute URL."""
    backend = NutanixPCBackend(client_factory=lambda *_: MagicMock())
    policy = _policy(scope={"host": "pc.example.com", "username": "admin", "password": "pw"})
    with pytest.raises(ValueError, match="Invalid nutanix_pc policy"):
        list(backend.run("bad", policy))
