#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""End-to-end dry-run style verification with fixture inventory (no live CV)."""

from pathlib import Path

import httpx
from worker.models import Config, Policy

from arista_cv.backend import AristaCVBackend
from arista_cv.client import CloudVisionClient

FIXTURES = Path(__file__).parent / "fixtures"


def test_dry_run_style_inventory_to_entities():
    """
    Simulate a dry-run: CloudVision Device/all response → Diode Device entities.

    Live CVaaS/CVP verification still requires CV_TOKEN and a reachable host;
    this covers the same code path with recorded inventory.
    """
    body = (FIXTURES / "devices_ndjson.txt").read_text()
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=body))

    def factory(scope, config):
        return CloudVisionClient(
            host=scope.host,
            token=scope.token,
            verify_ssl=scope.verify_ssl,
            timeout=config.timeout,
            transport=transport,
        )

    policy = Policy(
        config=Config.model_validate(
            {
                "package": "arista_cv",
                "defaults": {
                    "site": "lab",
                    "role": "leaf",
                    "manufacturer": "Arista",
                    "platform": "eos",
                    "tags": ["dry-run"],
                },
            }
        ),
        scope={
            "host": "https://www.arista.io",
            "token": "fixture-token-not-a-secret",
        },
    )

    entities = list(AristaCVBackend(client_factory=factory).run("dry_run", policy))
    assert len(entities) == 2
    names = sorted(e.device.name for e in entities)
    assert names == ["tp-avd-leaf1", "tp-avd-leaf4"]
    for entity in entities:
        assert entity.device.site.name == "lab"
        assert entity.device.serial
        assert entity.device.status == "active"
        # Token must never appear on entity payloads.
        assert "fixture-token" not in str(entity)
