#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""Tests for CiscoIntersightBackend policy handling."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from worker.backend import load_class
from worker.models import Config, Policy

from cisco_intersight.backend import APP_NAME, APP_VERSION, CiscoIntersightBackend
from cisco_intersight.models import IntersightDevice

SECRET_KEY = (Path(__file__).parent / "fixtures" / "test_secret_key.pem").read_text()


def _policy(**overrides) -> Policy:
    data = {
        "config": {
            "package": "cisco_intersight",
            "defaults": {
                "site": "dc1",
                "role": "server",
                "manufacturer": "Cisco",
                "platform": "ucs",
                "tags": ["intersight"],
            },
        },
        "scope": {
            "host": "https://intersight.com",
            "api_key_id": "test/api-key-id",
            "secret_key": SECRET_KEY,
        },
    }
    data.update(overrides)
    return Policy(config=Config(**data["config"]), scope=data["scope"])


def test_describe():
    """describe returns stable metadata."""
    meta = CiscoIntersightBackend.describe()
    assert meta.name == "cisco_intersight"
    assert meta.app_name == APP_NAME
    assert meta.app_version == APP_VERSION


def test_load_class_discovers_backend():
    """Worker load_class finds CiscoIntersightBackend via package import."""
    assert load_class("cisco_intersight") is CiscoIntersightBackend


def test_run_maps_devices_from_client():
    """run() uses the injected client and maps devices to entities."""
    mock_client = MagicMock()
    mock_client.list_devices.return_value = [
        IntersightDevice(
            device_id="62f1aaaaaaaaaaaaaaaaaaaa",
            hostname="ucs-c220-01",
            model_name="UCSC-C220-M5SX",
            software_version="4.2(1a)",
            mgmt_ip="10.30.1.11",
            serial="FCH1234567A",
            status="on",
        )
    ]

    backend = CiscoIntersightBackend(client_factory=lambda scope, config: mock_client)
    entities = list(backend.run("cisco_intersight_inventory", _policy()))

    mock_client.list_devices.assert_called_once_with(active_only=True)
    mock_client.close.assert_called_once()
    assert len(entities) == 1
    assert entities[0].device.name == "ucs-c220-01"
    assert entities[0].device.serial == "FCH1234567A"
    assert entities[0].device.site.name == "dc1"


def test_run_rejects_bad_package():
    """Wrong config.package fails validation."""
    backend = CiscoIntersightBackend(client_factory=lambda *_: MagicMock())
    policy = _policy(
        config={
            "package": "other",
            "defaults": {"site": "dc1"},
        }
    )
    with pytest.raises(ValueError, match="Invalid cisco_intersight policy"):
        list(backend.run("bad", policy))


def test_run_rejects_non_mapping_scope():
    """Scope must be a mapping."""
    backend = CiscoIntersightBackend(client_factory=lambda *_: MagicMock())
    policy = Policy(
        config=Config.model_validate(
            {
                "package": "cisco_intersight",
                "defaults": {"site": "dc1"},
            }
        ),
        scope=["not", "a", "map"],
    )
    with pytest.raises(ValueError, match="scope must be a mapping"):
        list(backend.run("bad", policy))


def test_run_rejects_missing_secret_key():
    """Missing secret_key fails scope validation."""
    backend = CiscoIntersightBackend(client_factory=lambda *_: MagicMock())
    policy = _policy(scope={"host": "https://intersight.com", "api_key_id": "kid"})
    with pytest.raises(ValueError, match="Invalid cisco_intersight policy"):
        list(backend.run("bad", policy))


def test_run_rejects_relative_host():
    """Host must be an absolute URL."""
    backend = CiscoIntersightBackend(client_factory=lambda *_: MagicMock())
    policy = _policy(scope={"host": "intersight.com", "api_key_id": "kid", "secret_key": SECRET_KEY})
    with pytest.raises(ValueError, match="Invalid cisco_intersight policy"):
        list(backend.run("bad", policy))
