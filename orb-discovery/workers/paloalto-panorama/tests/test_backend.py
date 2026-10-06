#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""Tests for PaloAltoPanoramaBackend policy handling."""

from unittest.mock import MagicMock

import pytest
from worker.backend import load_class
from worker.models import Config, Policy

from paloalto_panorama.backend import APP_NAME, APP_VERSION, PaloAltoPanoramaBackend
from paloalto_panorama.models import PanoramaDevice


def _policy(**overrides) -> Policy:
    data = {
        "config": {
            "package": "paloalto_panorama",
            "defaults": {
                "site": "dc1",
                "role": "firewall",
                "manufacturer": "Palo Alto Networks",
                "platform": "panos",
                "tags": ["panorama"],
            },
        },
        "scope": {
            "host": "https://panorama.example.com",
            "api_key": "test-api-key",
        },
    }
    data.update(overrides)
    return Policy(config=Config(**data["config"]), scope=data["scope"])


def test_describe():
    """describe returns stable metadata."""
    meta = PaloAltoPanoramaBackend.describe()
    assert meta.name == "paloalto_panorama"
    assert meta.app_name == APP_NAME
    assert meta.app_version == APP_VERSION


def test_load_class_discovers_backend():
    """Worker load_class finds PaloAltoPanoramaBackend via package import."""
    assert load_class("paloalto_panorama") is PaloAltoPanoramaBackend


def test_run_maps_devices_from_client():
    """run() uses the injected client and maps devices to entities."""
    mock_client = MagicMock()
    mock_client.list_devices.return_value = [
        PanoramaDevice(
            device_id="007051000111111",
            hostname="fw-edge-01",
            model_name="PA-3220",
            software_version="10.2.3",
            mgmt_ip="10.40.1.11",
            serial="007051000111111",
            status="yes",
        )
    ]

    backend = PaloAltoPanoramaBackend(client_factory=lambda scope, config: mock_client)
    entities = list(backend.run("paloalto_panorama_inventory", _policy()))

    mock_client.list_devices.assert_called_once_with(active_only=True)
    mock_client.close.assert_called_once()
    assert len(entities) == 1
    assert entities[0].device.name == "fw-edge-01"
    assert entities[0].device.serial == "007051000111111"
    assert entities[0].device.site.name == "dc1"


def test_run_rejects_bad_package():
    """Wrong config.package fails validation."""
    backend = PaloAltoPanoramaBackend(client_factory=lambda *_: MagicMock())
    policy = _policy(
        config={
            "package": "other",
            "defaults": {"site": "dc1"},
        }
    )
    with pytest.raises(ValueError, match="Invalid paloalto_panorama policy"):
        list(backend.run("bad", policy))


def test_run_rejects_non_mapping_scope():
    """Scope must be a mapping."""
    backend = PaloAltoPanoramaBackend(client_factory=lambda *_: MagicMock())
    policy = Policy(
        config=Config.model_validate(
            {
                "package": "paloalto_panorama",
                "defaults": {"site": "dc1"},
            }
        ),
        scope=["not", "a", "map"],
    )
    with pytest.raises(ValueError, match="scope must be a mapping"):
        list(backend.run("bad", policy))


def test_run_rejects_missing_api_key():
    """Missing api_key fails scope validation."""
    backend = PaloAltoPanoramaBackend(client_factory=lambda *_: MagicMock())
    policy = _policy(scope={"host": "https://panorama.example.com"})
    with pytest.raises(ValueError, match="Invalid paloalto_panorama policy"):
        list(backend.run("bad", policy))


def test_run_rejects_relative_host():
    """Host must be an absolute URL."""
    backend = PaloAltoPanoramaBackend(client_factory=lambda *_: MagicMock())
    policy = _policy(scope={"host": "panorama.example.com", "api_key": "k"})
    with pytest.raises(ValueError, match="Invalid paloalto_panorama policy"):
        list(backend.run("bad", policy))
