#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""Tests for the vCenter HTTP client."""

import json
from pathlib import Path

import httpx
import pytest

from vmware_vcenter.client import HOSTS_PATH, SESSION_HEADER, SESSION_PATH, VCenterClient, _parse_hosts_payload

FIXTURES = Path(__file__).parent / "fixtures"
SESSION_ID = "test-session-id-not-a-secret"


def test_parse_hosts_list_payload():
    """List payloads are parsed."""
    payload = json.loads((FIXTURES / "hosts_list.json").read_text())
    records = _parse_hosts_payload(payload)
    assert len(records) == 3
    assert records[0]["name"] == "esxi-01.lab.example.com"


def test_list_devices_active_only():
    """Client returns only CONNECTED hosts by default."""
    body = (FIXTURES / "hosts_list.json").read_text()
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        if request.url.path == SESSION_PATH and request.method == "POST":
            assert request.headers.get("authorization", "").startswith("Basic ")
            return httpx.Response(200, json=SESSION_ID)
        if request.url.path == HOSTS_PATH and request.method == "GET":
            assert request.headers.get(SESSION_HEADER) == SESSION_ID
            return httpx.Response(200, text=body)
        if request.url.path == SESSION_PATH and request.method == "DELETE":
            assert request.headers.get(SESSION_HEADER) == SESSION_ID
            return httpx.Response(200)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    with VCenterClient(
        "https://vcenter.example.com",
        "admin@vsphere.local",
        "secret-password",
        transport=transport,
    ) as client:
        devices = client.list_devices(active_only=True)

    assert SESSION_PATH in seen_paths
    assert HOSTS_PATH in seen_paths
    assert len(devices) == 2
    assert {d.hostname for d in devices} == {
        "esxi-01.lab.example.com",
        "esxi-02.lab.example.com",
    }
    assert devices[0].device_id == "host-11"
    assert devices[0].status == "CONNECTED"
    assert devices[0].power_state == "POWERED_ON"


def test_list_devices_includes_inactive():
    """active_only=False keeps disconnected hosts."""
    body = (FIXTURES / "hosts_list.json").read_text()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == SESSION_PATH and request.method == "POST":
            return httpx.Response(200, json=SESSION_ID)
        if request.url.path == HOSTS_PATH:
            return httpx.Response(200, text=body)
        if request.url.path == SESSION_PATH and request.method == "DELETE":
            return httpx.Response(200)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    with VCenterClient(
        "https://vcenter.example.com",
        "admin@vsphere.local",
        "pw",
        transport=transport,
    ) as client:
        devices = client.list_devices(active_only=False)
    assert len(devices) == 3
    assert "esxi-legacy.lab.example.com" in {d.hostname for d in devices}


def test_list_devices_http_error():
    """Non-success HTTP responses raise RuntimeError without leaking the body."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == SESSION_PATH and request.method == "POST":
            return httpx.Response(200, json=SESSION_ID)
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
