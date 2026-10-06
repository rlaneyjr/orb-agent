#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""End-to-end dry-run style verification with fixture inventory (no live Prism Central)."""

from pathlib import Path

import httpx
from worker.models import Config, Policy

from nutanix_pc.backend import NutanixPCBackend
from nutanix_pc.client import PrismCentralClient

FIXTURES = Path(__file__).parent / "fixtures"


def test_dry_run_style_inventory_to_entities():
    """
    Simulate a dry-run: Prism Central hosts/list response → Diode Device entities.

    Live Prism Central verification still requires credentials and a reachable host;
    this covers the same code path with recorded inventory.
    """
    body = (FIXTURES / "hosts_list.json").read_text()
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=body))

    def factory(scope, config):
        return PrismCentralClient(
            host=scope.host,
            username=scope.username,
            password=scope.password,
            verify_ssl=scope.verify_ssl,
            timeout=config.timeout,
            transport=transport,
        )

    policy = Policy(
        config=Config.model_validate(
            {
                "package": "nutanix_pc",
                "defaults": {
                    "site": "lab",
                    "role": "hypervisor",
                    "manufacturer": "Nutanix",
                    "platform": "ahv",
                    "tags": ["dry-run"],
                },
            }
        ),
        scope={
            "host": "https://pc.example.com:9440",
            "username": "admin",
            "password": "fixture-password-not-a-secret",
        },
    )

    entities = list(NutanixPCBackend(client_factory=factory).run("dry_run", policy))
    assert len(entities) == 2
    names = sorted(e.device.name for e in entities)
    assert names == ["NTNX-HOST-01", "NTNX-HOST-02"]
    for entity in entities:
        assert entity.device.site.name == "lab"
        assert entity.device.serial
        assert entity.device.status == "active"
        assert "fixture-password" not in str(entity)
