#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""Tests for the Panorama XML API client."""

from pathlib import Path

import httpx
import pytest

from paloalto_panorama.client import API_PATH, SHOW_DEVICES_ALL, PanoramaClient

FIXTURES = Path(__file__).parent / "fixtures"


def test_list_devices_active_only():
    """Client returns only connected devices by default."""
    body = (FIXTURES / "devices_all.xml").read_text()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.rstrip("/") == API_PATH.rstrip("/")
        assert request.headers["x-pan-key"] == "secret-api-key"
        assert request.method == "POST"
        form = dict(httpx.QueryParams(request.content.decode()))
        assert form.get("type") == "op"
        assert form.get("cmd") == SHOW_DEVICES_ALL
        return httpx.Response(200, text=body)

    transport = httpx.MockTransport(handler)
    with PanoramaClient(
        "https://panorama.example.com",
        "secret-api-key",
        transport=transport,
    ) as client:
        devices = client.list_devices(active_only=True)

    assert len(devices) == 2
    assert {d.hostname for d in devices} == {"fw-edge-01", "fw-edge-02"}
    assert devices[0].serial == "007051000111111"
    assert devices[0].model_name == "PA-3220"
    assert devices[0].software_version == "10.2.3"
    assert devices[0].mgmt_ip == "10.40.1.11"
    assert devices[0].device_group == "edge-dg"


def test_list_devices_includes_inactive():
    """active_only=False keeps disconnected devices."""
    body = (FIXTURES / "devices_all.xml").read_text()
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=body))
    with PanoramaClient("https://panorama.example.com", "tok", transport=transport) as client:
        devices = client.list_devices(active_only=False)
    assert len(devices) == 3
    assert "fw-legacy" in {d.hostname for d in devices}


def test_list_devices_http_error():
    """Non-success HTTP responses raise RuntimeError without leaking the body."""
    transport = httpx.MockTransport(lambda request: httpx.Response(401, text="unauthorized api_key=leak"))
    with PanoramaClient("https://panorama.example.com", "tok", transport=transport) as client:
        with pytest.raises(RuntimeError, match="HTTP 401") as exc_info:
            client.list_devices()
    assert "leak" not in str(exc_info.value)


def test_list_devices_xml_error_status():
    """Panorama XML status!=success raises RuntimeError."""
    body = '<?xml version="1.0"?><response status="error"><msg>denied</msg></response>'
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=body))
    with PanoramaClient("https://panorama.example.com", "tok", transport=transport) as client:
        with pytest.raises(RuntimeError, match="status=error"):
            client.list_devices()
