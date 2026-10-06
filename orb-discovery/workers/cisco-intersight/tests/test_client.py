#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""Tests for the Intersight HTTP client."""

import json
from pathlib import Path

import httpx
import pytest

from cisco_intersight.client import PHYSICAL_SUMMARIES_PATH, IntersightClient, _parse_results_payload

FIXTURES = Path(__file__).parent / "fixtures"
SECRET_KEY = (FIXTURES / "test_secret_key.pem").read_text()


def test_parse_results_payload():
    """Results-wrapped payloads are parsed."""
    payload = json.loads((FIXTURES / "physical_summaries.json").read_text())
    records = _parse_results_payload(payload)
    assert len(records) == 3
    assert records[0]["Name"] == "ucs-c220-01"


def test_list_devices_active_only():
    """Client returns only powered-on devices by default and signs requests."""
    body = (FIXTURES / "physical_summaries.json").read_text()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == PHYSICAL_SUMMARIES_PATH
        assert request.headers["authorization"].startswith("Signature keyId=")
        assert "Digest" in request.headers
        assert "Date" in request.headers
        assert SECRET_KEY.splitlines()[1] not in (request.content.decode() if request.content else "")
        return httpx.Response(200, text=body)

    transport = httpx.MockTransport(handler)
    with IntersightClient(
        "https://intersight.com",
        "test/api-key-id",
        SECRET_KEY,
        transport=transport,
    ) as client:
        devices = client.list_devices(active_only=True)

    assert len(devices) == 2
    assert {d.hostname for d in devices} == {"ucs-c220-01", "ucs-c220-02"}
    assert devices[0].serial == "FCH1234567A"
    assert devices[0].model_name == "UCSC-C220-M5SX"
    assert devices[0].mgmt_ip == "10.30.1.11"


def test_list_devices_includes_inactive():
    """active_only=False keeps powered-off devices."""
    body = (FIXTURES / "physical_summaries.json").read_text()
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=body))
    with IntersightClient(
        "https://intersight.com",
        "test/api-key-id",
        SECRET_KEY,
        transport=transport,
    ) as client:
        devices = client.list_devices(active_only=False)
    assert len(devices) == 3
    assert "ucs-legacy" in {d.hostname for d in devices}


def test_list_devices_http_error():
    """Non-success HTTP responses raise RuntimeError without leaking the body."""
    transport = httpx.MockTransport(lambda request: httpx.Response(401, text="unauthorized secret=leak"))
    with IntersightClient("https://intersight.com", "kid", SECRET_KEY, transport=transport) as client:
        with pytest.raises(RuntimeError, match="HTTP 401") as exc_info:
            client.list_devices()
    assert "leak" not in str(exc_info.value)
