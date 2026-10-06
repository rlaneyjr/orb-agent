#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""End-to-end dry-run style verification with fixture inventory (no live Control)."""

from pathlib import Path

import httpx
from worker.models import Config, Policy

from a10_control.backend import A10ControlBackend
from a10_control.client import A10ControlClient

FIXTURES = Path(__file__).parent / "fixtures"


def test_dry_run_style_inventory_to_entities():
    """
    Simulate a dry-run: A10 Control device-list response → Diode Device entities.

    Live Control verification still requires A10_API_KEY and a reachable host;
    this covers the same code path with recorded inventory.
    """
    body = (FIXTURES / "devices_list.json").read_text()
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=body))

    def factory(scope, config):
        return A10ControlClient(
            host=scope.host,
            api_key=scope.api_key,
            organization=scope.organization,
            verify_ssl=scope.verify_ssl,
            timeout=config.timeout,
            transport=transport,
        )

    policy = Policy(
        config=Config.model_validate(
            {
                "package": "a10_control",
                "defaults": {
                    "site": "lab",
                    "role": "load-balancer",
                    "manufacturer": "A10 Networks",
                    "platform": "acos",
                    "tags": ["dry-run"],
                },
            }
        ),
        scope={
            "host": "https://control.example.com",
            "api_key": "fixture-api-key-not-a-secret",
            "organization": "root",
        },
    )

    entities = list(A10ControlBackend(client_factory=factory).run("dry_run", policy))
    assert len(entities) == 2
    names = sorted(e.device.name for e in entities)
    assert names == ["thunder-adc-01", "thunder-adc-02"]
    for entity in entities:
        assert entity.device.site.name == "lab"
        assert entity.device.serial
        assert entity.device.status == "active"
        # API key must never appear on entity payloads.
        assert "fixture-api-key" not in str(entity)
