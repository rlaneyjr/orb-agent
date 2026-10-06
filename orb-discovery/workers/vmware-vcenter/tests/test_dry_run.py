#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""End-to-end dry-run style verification with fixture inventory (no live vCenter)."""

from pathlib import Path

import httpx
from worker.models import Config, Policy

from vmware_vcenter.backend import VMwareVCenterBackend
from vmware_vcenter.client import HOSTS_PATH, SESSION_PATH, VCenterClient

FIXTURES = Path(__file__).parent / "fixtures"
SESSION_ID = "fixture-session-id"


def test_dry_run_style_inventory_to_entities():
    """
    Simulate a dry-run: vCenter host list response → Diode Device entities.

    Live vCenter verification still requires credentials and a reachable host;
    this covers the same code path with recorded inventory.
    """
    body = (FIXTURES / "hosts_list.json").read_text()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == SESSION_PATH and request.method == "POST":
            return httpx.Response(200, json=SESSION_ID)
        if request.url.path == HOSTS_PATH:
            return httpx.Response(200, text=body)
        if request.url.path == SESSION_PATH and request.method == "DELETE":
            return httpx.Response(200)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)

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
    assert len(entities) == 2
    names = sorted(e.device.name for e in entities)
    assert names == ["esxi-01.lab.example.com", "esxi-02.lab.example.com"]
    for entity in entities:
        assert entity.device.site.name == "lab"
        assert entity.device.serial
        assert entity.device.status == "active"
        assert "fixture-password" not in str(entity)
