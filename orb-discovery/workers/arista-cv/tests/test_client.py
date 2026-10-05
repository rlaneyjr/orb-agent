#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""Tests for the CloudVision HTTP client."""

from pathlib import Path

import httpx
import pytest

from arista_cv.client import DEVICES_PATH, CloudVisionClient, _parse_inventory_payload

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_ndjson_payload():
    """Concatenated JSON objects from Device/all are parsed."""
    text = (FIXTURES / "devices_ndjson.txt").read_text()
    records = _parse_inventory_payload(text)
    assert len(records) == 3
    assert records[0]["result"]["value"]["hostname"] == "tp-avd-leaf4"


def test_parse_wrapped_payload():
    """cvprac-style {\"data\": [...]} payloads are parsed."""
    text = (FIXTURES / "devices_wrapped.json").read_text()
    records = _parse_inventory_payload(text)
    assert len(records) == 2
    assert records[1]["result"]["value"]["hostname"] == "leaf-02"


def test_list_devices_active_only():
    """Client returns only STREAMING_STATUS_ACTIVE devices by default."""
    body = (FIXTURES / "devices_ndjson.txt").read_text()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == DEVICES_PATH
        assert request.headers["Authorization"] == "Bearer secret-token"
        assert "secret-token" not in (request.content.decode() if request.content else "")
        return httpx.Response(200, text=body)

    transport = httpx.MockTransport(handler)
    with CloudVisionClient(
        "https://www.arista.io",
        "secret-token",
        transport=transport,
    ) as client:
        devices = client.list_devices(active_only=True)

    assert len(devices) == 2
    assert {d.hostname for d in devices} == {"tp-avd-leaf4", "tp-avd-leaf1"}
    assert devices[0].device_id == "6323DA7D2B542B5D09630F87351BEA41"
    assert devices[0].model_name == "vEOS-lab"
    assert devices[0].software_version == "4.27.0F"


def test_list_devices_includes_inactive():
    """active_only=False keeps inactive devices."""
    body = (FIXTURES / "devices_ndjson.txt").read_text()
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=body))
    with CloudVisionClient("https://cvp.example.com", "tok", transport=transport) as client:
        devices = client.list_devices(active_only=False)
    assert len(devices) == 3
    assert "old-spine1" in {d.hostname for d in devices}


def test_list_devices_http_error():
    """Non-success HTTP responses raise RuntimeError without leaking the body."""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(401, text="unauthorized token=leak")
    )
    with CloudVisionClient("https://www.arista.io", "tok", transport=transport) as client:
        with pytest.raises(RuntimeError, match="HTTP 401") as exc_info:
            client.list_devices()
    assert "leak" not in str(exc_info.value)


def test_list_devices_wrapped_json():
    """Wrapped JSON inventory responses map correctly."""
    body = (FIXTURES / "devices_wrapped.json").read_text()
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=body))
    with CloudVisionClient("https://www.arista.io", "tok", transport=transport) as client:
        devices = client.list_devices()
    assert [d.hostname for d in devices] == ["leaf-01", "leaf-02"]
    assert devices[0].device_id == "JPE15214224"
