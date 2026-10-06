#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""End-to-end dry-run style verification with fixture inventory (no live Panorama)."""

from pathlib import Path

import httpx
from worker.models import Config, Policy

from paloalto_panorama.backend import PaloAltoPanoramaBackend
from paloalto_panorama.client import PanoramaClient

FIXTURES = Path(__file__).parent / "fixtures"


def test_dry_run_style_inventory_to_entities():
    """
    Simulate a dry-run: Panorama show devices all → Diode Device entities.

    Live Panorama verification still requires an API key and a reachable host;
    this covers the same code path with recorded inventory.
    """
    body = (FIXTURES / "devices_all.xml").read_text()
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=body))

    def factory(scope, config):
        return PanoramaClient(
            host=scope.host,
            api_key=scope.api_key,
            verify_ssl=scope.verify_ssl,
            timeout=config.timeout,
            transport=transport,
        )

    policy = Policy(
        config=Config.model_validate(
            {
                "package": "paloalto_panorama",
                "defaults": {
                    "site": "lab",
                    "role": "firewall",
                    "manufacturer": "Palo Alto Networks",
                    "platform": "panos",
                    "tags": ["dry-run"],
                },
            }
        ),
        scope={
            "host": "https://panorama.example.com",
            "api_key": "fixture-api-key-not-a-secret",
        },
    )

    entities = list(PaloAltoPanoramaBackend(client_factory=factory).run("dry_run", policy))
    assert len(entities) == 2
    names = sorted(e.device.name for e in entities)
    assert names == ["fw-edge-01", "fw-edge-02"]
    for entity in entities:
        assert entity.device.site.name == "lab"
        assert entity.device.serial
        assert entity.device.status == "active"
        assert "fixture-api-key" not in str(entity)
