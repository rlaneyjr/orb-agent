#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""Tests for the vCenter HTTP client."""

import httpx
import pytest
from inventory_fixtures import SESSION_ID, fixture_json, inventory_handler

from vmware_vcenter.client import (
    CLUSTERS_PATH,
    HOSTS_PATH,
    SESSION_PATH,
    VCenterClient,
    _parse_hosts_payload,
)


def test_parse_hosts_list_payload():
    """List payloads are parsed."""
    records = _parse_hosts_payload(fixture_json("hosts_list.json"))
    assert len(records) == 3
    assert records[0]["name"] == "esxi-01.lab.example.com"


def test_list_clusters():
    """Client returns cluster inventory."""
    transport = httpx.MockTransport(inventory_handler)
    with VCenterClient(
        "https://vcenter.example.com",
        "admin@vsphere.local",
        "secret-password",
        transport=transport,
    ) as client:
        clusters = client.list_clusters()

    assert len(clusters) == 2
    assert clusters[0].cluster_id == "domain-c21"
    assert clusters[0].name == "prod-cluster-a"
    assert clusters[0].ha_enabled is True
    assert clusters[1].name == "lab-cluster"


def test_list_devices_active_only():
    """Client returns only CONNECTED hosts by default, with cluster names."""
    transport = httpx.MockTransport(inventory_handler)
    with VCenterClient(
        "https://vcenter.example.com",
        "admin@vsphere.local",
        "secret-password",
        transport=transport,
    ) as client:
        devices = client.list_devices(active_only=True)

    assert len(devices) == 2
    assert {d.hostname for d in devices} == {
        "esxi-01.lab.example.com",
        "esxi-02.lab.example.com",
    }
    assert devices[0].device_id == "host-11"
    assert devices[0].status == "CONNECTED"
    assert devices[0].power_state == "POWERED_ON"
    by_name = {d.hostname: d for d in devices}
    assert by_name["esxi-01.lab.example.com"].cluster_name == "prod-cluster-a"
    assert by_name["esxi-02.lab.example.com"].cluster_name == "prod-cluster-a"


def test_list_devices_includes_inactive():
    """active_only=False keeps disconnected hosts."""
    transport = httpx.MockTransport(inventory_handler)
    with VCenterClient(
        "https://vcenter.example.com",
        "admin@vsphere.local",
        "pw",
        transport=transport,
    ) as client:
        devices = client.list_devices(active_only=False)
    assert len(devices) == 3
    by_name = {d.hostname: d for d in devices}
    assert "esxi-legacy.lab.example.com" in by_name
    assert by_name["esxi-legacy.lab.example.com"].cluster_name == "lab-cluster"


def test_list_vms_active_only():
    """Client returns powered-on VMs with cluster and host links."""
    transport = httpx.MockTransport(inventory_handler)
    with VCenterClient(
        "https://vcenter.example.com",
        "admin@vsphere.local",
        "pw",
        transport=transport,
    ) as client:
        vms = client.list_vms(active_only=True)

    assert len(vms) == 2
    by_name = {v.name: v for v in vms}
    assert by_name["web-01"].cluster_name == "prod-cluster-a"
    assert by_name["web-01"].host_name == "esxi-01.lab.example.com"
    assert by_name["web-01"].cpu_count == 4
    assert by_name["web-01"].memory_mib == 8192
    assert by_name["db-01"].host_name == "esxi-02.lab.example.com"


def test_list_vms_includes_inactive():
    """active_only=False keeps powered-off VMs."""
    transport = httpx.MockTransport(inventory_handler)
    with VCenterClient(
        "https://vcenter.example.com",
        "admin@vsphere.local",
        "pw",
        transport=transport,
    ) as client:
        vms = client.list_vms(active_only=False)
    assert len(vms) == 3
    assert "retired-app" in {v.name for v in vms}


def test_list_devices_http_error():
    """Non-success HTTP responses raise RuntimeError without leaking the body."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == SESSION_PATH and request.method == "POST":
            return httpx.Response(200, json=SESSION_ID)
        if request.url.path == CLUSTERS_PATH:
            return httpx.Response(200, json=[])
        if request.url.path == HOSTS_PATH:
            return httpx.Response(401, text="unauthorized password=leak")
        if request.url.path == SESSION_PATH and request.method == "DELETE":
            return httpx.Response(200)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    with VCenterClient("https://vcenter.example.com", "admin", "pw", transport=transport) as client:
        with pytest.raises(RuntimeError, match="HTTP 401") as exc_info:
            client.list_devices()
    assert "leak" not in str(exc_info.value)
    assert SESSION_ID not in str(exc_info.value)


def test_session_http_error():
    """Session failures raise RuntimeError without leaking the body."""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(403, text="forbidden password=leak session=abc")
    )
    with VCenterClient("https://vcenter.example.com", "admin", "pw", transport=transport) as client:
        with pytest.raises(RuntimeError, match="session request failed: HTTP 403") as exc_info:
            client.list_devices()
    assert "leak" not in str(exc_info.value)
