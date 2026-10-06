#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""Tests for the Prism Central HTTP client."""

import json
from pathlib import Path

import httpx
import pytest

from nutanix_pc.client import HOSTS_LIST_PATH, PrismCentralClient, _parse_hosts_payload

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_hosts_list_payload():
    """entities-wrapped payloads are parsed."""
    payload = json.loads((FIXTURES / "hosts_list.json").read_text())
    records = _parse_hosts_payload(payload)
    assert len(records) == 3
    assert records[0]["status"]["name"] == "NTNX-HOST-01"


def test_list_devices_active_only():
    """Client returns only complete hosts by default."""
    body = (FIXTURES / "hosts_list.json").read_text()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == HOSTS_LIST_PATH
        assert request.method == "POST"
        assert request.headers.get("authorization", "").startswith("Basic ")
        return httpx.Response(200, text=body)

    transport = httpx.MockTransport(handler)
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


def test_list_devices_includes_inactive():
    """active_only=False keeps error-state hosts."""
    body = (FIXTURES / "hosts_list.json").read_text()
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=body))
    with PrismCentralClient(
        "https://pc.example.com:9440",
        "admin",
        "pw",
        transport=transport,
    ) as client:
        devices = client.list_devices(active_only=False)
    assert len(devices) == 3
    assert "NTNX-HOST-LEGACY" in {d.hostname for d in devices}


def test_list_devices_http_error():
    """Non-success HTTP responses raise RuntimeError without leaking the body."""
    transport = httpx.MockTransport(lambda request: httpx.Response(401, text="unauthorized password=leak"))
    with PrismCentralClient("https://pc.example.com:9440", "admin", "pw", transport=transport) as client:
        with pytest.raises(RuntimeError, match="HTTP 401") as exc_info:
            client.list_devices()
    assert "leak" not in str(exc_info.value)
