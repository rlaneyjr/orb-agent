#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""End-to-end dry-run style verification with fixture inventory (no live Intersight)."""

from pathlib import Path

import httpx
from worker.models import Config, Policy

from cisco_intersight.backend import CiscoIntersightBackend
from cisco_intersight.client import IntersightClient

FIXTURES = Path(__file__).parent / "fixtures"
SECRET_KEY = (FIXTURES / "test_secret_key.pem").read_text()


def test_dry_run_style_inventory_to_entities():
    """
    Simulate a dry-run: Intersight PhysicalSummaries → Diode Device entities.

    Live Intersight verification still requires a real API key; this covers the
    same code path with recorded inventory.
    """
    body = (FIXTURES / "physical_summaries.json").read_text()
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=body))

    def factory(scope, config):
        return IntersightClient(
            host=scope.host,
            api_key_id=scope.api_key_id,
            secret_key=scope.secret_key,
            verify_ssl=scope.verify_ssl,
            timeout=config.timeout,
            transport=transport,
        )

    policy = Policy(
        config=Config.model_validate(
            {
                "package": "cisco_intersight",
                "defaults": {
                    "site": "lab",
                    "role": "server",
                    "manufacturer": "Cisco",
                    "platform": "ucs",
                    "tags": ["dry-run"],
                },
            }
        ),
        scope={
            "host": "https://intersight.com",
            "api_key_id": "fixture/api-key-id",
            "secret_key": SECRET_KEY,
        },
    )

    entities = list(CiscoIntersightBackend(client_factory=factory).run("dry_run", policy))
    assert len(entities) == 2
    names = sorted(e.device.name for e in entities)
    assert names == ["ucs-c220-01", "ucs-c220-02"]
    for entity in entities:
        assert entity.device.site.name == "lab"
        assert entity.device.serial
        assert entity.device.status == "active"
        assert "BEGIN RSA PRIVATE KEY" not in str(entity)
