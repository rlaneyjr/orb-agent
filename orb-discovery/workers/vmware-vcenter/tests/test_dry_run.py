#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""End-to-end dry-run style verification with fixture inventory (no live vCenter)."""

import httpx
from inventory_fixtures import inventory_handler
from worker.models import Config, Policy

from vmware_vcenter.backend import VMwareVCenterBackend
from vmware_vcenter.client import VCenterClient


def test_dry_run_style_inventory_to_entities():
    """
    Simulate a dry-run: vCenter inventory responses → Diode entities.

    Live vCenter verification still requires credentials and a reachable host;
    this covers the same code path with recorded inventory.
    """
    transport = httpx.MockTransport(lambda req: inventory_handler(req, session_id="fixture-session-id"))

    def factory(scope, config):
        return VCenterClient(
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
                "package": "vmware_vcenter",
                "defaults": {
                    "site": "lab",
                    "role": "hypervisor",
                    "manufacturer": "VMware",
                    "platform": "esxi",
                    "tags": ["dry-run"],
                },
            }
        ),
        scope={
            "host": "https://vcenter.example.com",
            "username": "admin@vsphere.local",
            "password": "fixture-password-not-a-secret",
        },
    )

    entities = list(VMwareVCenterBackend(client_factory=factory).run("dry_run", policy))
    by_kind: dict[str, list] = {}
    for entity in entities:
        by_kind.setdefault(entity.WhichOneof("entity"), []).append(entity)

    assert {e.cluster.name for e in by_kind["cluster"]} == {"prod-cluster-a", "lab-cluster"}
    assert {e.device.name for e in by_kind["device"]} == {
        "esxi-01.lab.example.com",
        "esxi-02.lab.example.com",
    }
    assert {e.virtual_machine.name for e in by_kind["virtual_machine"]} == {"web-01", "db-01"}
    for entity in by_kind["device"]:
        assert entity.device.site.name == "lab"
        assert entity.device.serial
        assert entity.device.status == "active"
        assert "fixture-password" not in str(entity)
