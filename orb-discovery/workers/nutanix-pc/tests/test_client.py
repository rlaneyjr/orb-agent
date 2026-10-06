#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""Tests for the Prism Central HTTP client."""

import json
from pathlib import Path

import httpx
import pytest

from nutanix_pc.client import (
    CLUSTERS_LIST_PATH,
    HOSTS_LIST_PATH,
    VMS_LIST_PATH,
    PrismCentralClient,
    _parse_hosts_payload,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def _inventory_handler(request: httpx.Request) -> httpx.Response:
    assert request.method == "POST"
    assert request.headers.get("authorization", "").startswith("Basic ")
    if request.url.path == HOSTS_LIST_PATH:
        return httpx.Response(200, text=_fixture("hosts_list.json"))
    if request.url.path == CLUSTERS_LIST_PATH:
        return httpx.Response(200, text=_fixture("clusters_list.json"))
    if request.url.path == VMS_LIST_PATH:
        return httpx.Response(200, text=_fixture("vms_list.json"))
    return httpx.Response(404)


def test_parse_hosts_list_payload():
    """entities-wrapped payloads are parsed."""
    payload = json.loads(_fixture("hosts_list.json"))
    records = _parse_hosts_payload(payload)
    assert len(records) == 3
    assert records[0]["status"]["name"] == "NTNX-HOST-01"


def test_list_clusters():
    """Client returns cluster inventory."""
    transport = httpx.MockTransport(_inventory_handler)
    with PrismCentralClient(
        "https://pc.example.com:9440",
        "admin",
        "secret-password",
        transport=transport,
    ) as client:
        clusters = client.list_clusters()

    assert len(clusters) == 2
    assert clusters[0].name == "prod-cluster-a"
    assert clusters[0].cluster_id == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert clusters[1].name == "legacy-cluster"


def test_list_devices_active_only():
    """Client returns only complete hosts by default."""
    transport = httpx.MockTransport(_inventory_handler)
    with PrismCentralClient(
        "https://pc.example.com:9440",
        "admin",
        "secret-password",
        transport=transport,
    ) as client:
        devices = client.list_devices(active_only=True)

    assert len(devices) == 2
    assert {d.hostname for d in devices} == {"NTNX-HOST-01", "NTNX-HOST-02"}
    assert devices[0].serial == "19SM6H230123"
    assert devices[0].model_name == "NX-1065-G7"
    assert devices[0].mgmt_ip == "10.20.1.11"
    assert devices[0].cluster_name == "prod-cluster-a"


def test_list_devices_includes_inactive():
    """active_only=False keeps error-state hosts."""
    transport = httpx.MockTransport(_inventory_handler)
    with PrismCentralClient(
        "https://pc.example.com:9440",
        "admin",
        "pw",
        transport=transport,
    ) as client:
        devices = client.list_devices(active_only=False)
    assert len(devices) == 3
    assert "NTNX-HOST-LEGACY" in {d.hostname for d in devices}


def test_list_vms_active_only():
    """Client returns powered-on VMs with cluster/host/resources."""
    transport = httpx.MockTransport(_inventory_handler)
    with PrismCentralClient(
        "https://pc.example.com:9440",
        "admin",
        "pw",
        transport=transport,
    ) as client:
        vms = client.list_vms(active_only=True)

    assert len(vms) == 2
    by_name = {v.name: v for v in vms}
    assert by_name["web-01"].cluster_name == "prod-cluster-a"
    assert by_name["web-01"].host_name == "NTNX-HOST-01"
    assert by_name["web-01"].cpu_count == 4
    assert by_name["web-01"].memory_mib == 8192
    assert by_name["web-01"].disk_gb == 150  # 51200+102400 MiB → 150 GiB
    assert by_name["web-01"].primary_ip == "10.20.2.10"
    assert by_name["db-01"].host_name == "NTNX-HOST-02"


def test_list_vms_includes_inactive():
    """active_only=False keeps powered-off VMs."""
    transport = httpx.MockTransport(_inventory_handler)
    with PrismCentralClient(
        "https://pc.example.com:9440",
        "admin",
        "pw",
        transport=transport,
    ) as client:
        vms = client.list_vms(active_only=False)
    assert len(vms) == 3
    assert "retired-app" in {v.name for v in vms}


def test_list_devices_http_error():
    """Non-success HTTP responses raise RuntimeError without leaking the body."""
    transport = httpx.MockTransport(lambda request: httpx.Response(401, text="unauthorized password=leak"))
    with PrismCentralClient("https://pc.example.com:9440", "admin", "pw", transport=transport) as client:
        with pytest.raises(RuntimeError, match="HTTP 401") as exc_info:
            client.list_devices()
    assert "leak" not in str(exc_info.value)
