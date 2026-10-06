#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""Tests for the A10 Control HTTP client."""

import json
from pathlib import Path

import httpx
import pytest

from a10_control.client import (
    ACAPI_PREFIX,
    CLUSTERS_PATH,
    DEVICES_PATH,
    A10ControlClient,
    _parse_device_payload,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_device_list_payload():
    """device-list wrapped payloads are parsed."""
    payload = json.loads((FIXTURES / "devices_list.json").read_text())
    records = _parse_device_payload(payload)
    assert len(records) == 3
    assert records[0]["hostname"] == "thunder-adc-01"


def test_list_devices_active_only():
    """Client returns only connected devices by default."""
    body = (FIXTURES / "devices_list.json").read_text()
    org = "root"
    expected_path = f"{ACAPI_PREFIX}/{org}{DEVICES_PATH}"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == expected_path
        assert request.headers["x-api-key"] == "secret-api-key"
        assert "secret-api-key" not in (request.content.decode() if request.content else "")
        return httpx.Response(200, text=body)

    transport = httpx.MockTransport(handler)
    with A10ControlClient(
        "https://control.example.com",
        "secret-api-key",
        org,
        transport=transport,
    ) as client:
        devices = client.list_devices(active_only=True)

    assert len(devices) == 2
    assert {d.hostname for d in devices} == {"thunder-adc-01", "thunder-adc-02"}
    assert devices[0].serial == "AX12345678"
    assert devices[0].model_name == "Thunder 1040S"
    assert devices[0].software_version == "5.2.1-P6"
    assert devices[0].mgmt_ip == "10.10.1.11"


def test_list_devices_includes_inactive():
    """active_only=False keeps disconnected devices."""
    body = (FIXTURES / "devices_list.json").read_text()
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=body))
    with A10ControlClient(
        "https://control.example.com",
        "tok",
        "acme",
        transport=transport,
    ) as client:
        devices = client.list_devices(active_only=False)
    assert len(devices) == 3
    assert "thunder-legacy" in {d.hostname for d in devices}


def test_list_devices_http_error():
    """Non-success HTTP responses raise RuntimeError without leaking the body."""
    transport = httpx.MockTransport(lambda request: httpx.Response(401, text="unauthorized api_key=leak"))
    with A10ControlClient("https://control.example.com", "tok", "root", transport=transport) as client:
        with pytest.raises(RuntimeError, match="HTTP 401") as exc_info:
            client.list_devices()
    assert "leak" not in str(exc_info.value)


def test_list_devices_falls_back_to_clusters():
    """When /device/ is 404, devices are extracted from /cluster/."""
    cluster_body = (FIXTURES / "clusters_with_devices.json").read_text()
    org = "root"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(DEVICES_PATH.rstrip("/")) or request.url.path.endswith(DEVICES_PATH):
            return httpx.Response(404, text="not found")
        if CLUSTERS_PATH.rstrip("/") in request.url.path:
            return httpx.Response(200, text=cluster_body)
        return httpx.Response(500, text="unexpected")

    transport = httpx.MockTransport(handler)
    with A10ControlClient(
        "https://control.example.com",
        "tok",
        org,
        transport=transport,
    ) as client:
        devices = client.list_devices(active_only=True)

    assert len(devices) == 2
    assert {d.hostname for d in devices} == {"thunder-adc-01", "thunder-adc-02"}
    assert devices[0].cluster_name == "adc-cluster-a"
    assert devices[0].mgmt_ip == "10.10.1.11"
