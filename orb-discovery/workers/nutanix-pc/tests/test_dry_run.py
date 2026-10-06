#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""End-to-end dry-run style verification with fixture inventory (no live Prism Central)."""

from pathlib import Path

import httpx
from worker.models import Config, Policy

from nutanix_pc.backend import NutanixPCBackend
from nutanix_pc.client import CLUSTERS_LIST_PATH, HOSTS_LIST_PATH, VMS_LIST_PATH, PrismCentralClient

FIXTURES = Path(__file__).parent / "fixtures"


def test_dry_run_style_inventory_to_entities():
    """
    Simulate a dry-run: Prism Central inventory responses → Diode entities.

    Live Prism Central verification still requires credentials and a reachable host;
    this covers the same code path with recorded inventory.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == HOSTS_LIST_PATH:
            return httpx.Response(200, text=(FIXTURES / "hosts_list.json").read_text())
        if request.url.path == CLUSTERS_LIST_PATH:
            return httpx.Response(200, text=(FIXTURES / "clusters_list.json").read_text())
        if request.url.path == VMS_LIST_PATH:
            return httpx.Response(200, text=(FIXTURES / "vms_list.json").read_text())
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)

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
    by_kind: dict[str, list] = {}
    for entity in entities:
        kind = entity.WhichOneof("entity")
        by_kind.setdefault(kind, []).append(entity)

    assert len(by_kind["cluster"]) == 2
    assert {e.cluster.name for e in by_kind["cluster"]} == {"prod-cluster-a", "legacy-cluster"}
    assert len(by_kind["device"]) == 2
    assert {e.device.name for e in by_kind["device"]} == {"NTNX-HOST-01", "NTNX-HOST-02"}
    assert len(by_kind["virtual_machine"]) == 2
    assert {e.virtual_machine.name for e in by_kind["virtual_machine"]} == {"web-01", "db-01"}
    for entity in by_kind["device"]:
        assert entity.device.site.name == "lab"
        assert entity.device.serial
        assert entity.device.status == "active"
        assert entity.device.cluster.name == "prod-cluster-a"
        assert "fixture-password" not in str(entity)
