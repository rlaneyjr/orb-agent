#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""Tests for A10ControlBackend policy handling."""

from unittest.mock import MagicMock

import pytest
from worker.backend import load_class
from worker.models import Config, Policy

from a10_control.backend import APP_NAME, APP_VERSION, A10ControlBackend
from a10_control.models import A10Device


def _policy(**overrides) -> Policy:
    data = {
        "config": {
            "package": "a10_control",
            "defaults": {
                "site": "dc1",
                "role": "load-balancer",
                "manufacturer": "A10 Networks",
                "platform": "acos",
                "tags": ["a10"],
            },
        },
        "scope": {
            "host": "https://control.example.com",
            "api_key": "test-api-key",
            "organization": "root",
        },
    }
    data.update(overrides)
    return Policy(config=Config(**data["config"]), scope=data["scope"])


def test_describe():
    """describe returns stable metadata."""
    meta = A10ControlBackend.describe()
    assert meta.name == "a10_control"
    assert meta.app_name == APP_NAME
    assert meta.app_version == APP_VERSION


def test_load_class_discovers_backend():
    """Worker load_class finds A10ControlBackend via package import."""
    assert load_class("a10_control") is A10ControlBackend


def test_run_maps_devices_from_client():
    """run() uses the injected client and maps devices to entities."""
    mock_client = MagicMock()
    mock_client.list_devices.return_value = [
        A10Device(
            device_id="AX12345678",
            hostname="thunder-adc-01",
            model_name="Thunder 1040S",
            software_version="5.2.1-P6",
            mgmt_ip="10.10.1.11",
            serial="AX12345678",
            status="connected",
        )
    ]

    backend = A10ControlBackend(client_factory=lambda scope, config: mock_client)
    entities = list(backend.run("a10_control_inventory", _policy()))

    mock_client.list_devices.assert_called_once_with(active_only=True)
    mock_client.close.assert_called_once()
    assert len(entities) == 1
    assert entities[0].device.name == "thunder-adc-01"
    assert entities[0].device.serial == "AX12345678"
    assert entities[0].device.site.name == "dc1"


def test_run_rejects_bad_package():
    """Wrong config.package fails validation."""
    backend = A10ControlBackend(client_factory=lambda *_: MagicMock())
    policy = _policy(
        config={
            "package": "other",
            "defaults": {"site": "dc1"},
        }
    )
    with pytest.raises(ValueError, match="Invalid a10_control policy"):
        list(backend.run("bad", policy))


def test_run_rejects_non_mapping_scope():
    """Scope must be a mapping."""
    backend = A10ControlBackend(client_factory=lambda *_: MagicMock())
    policy = Policy(
        config=Config.model_validate(
            {
                "package": "a10_control",
                "defaults": {"site": "dc1"},
            }
        ),
        scope=["not", "a", "map"],
    )
    with pytest.raises(ValueError, match="scope must be a mapping"):
        list(backend.run("bad", policy))


def test_run_rejects_missing_api_key():
    """Missing api_key fails scope validation."""
    backend = A10ControlBackend(client_factory=lambda *_: MagicMock())
    policy = _policy(scope={"host": "https://control.example.com"})
    with pytest.raises(ValueError, match="Invalid a10_control policy"):
        list(backend.run("bad", policy))


def test_run_rejects_relative_host():
    """Host must be an absolute URL."""
    backend = A10ControlBackend(client_factory=lambda *_: MagicMock())
    policy = _policy(scope={"host": "control.example.com", "api_key": "k"})
    with pytest.raises(ValueError, match="Invalid a10_control policy"):
        list(backend.run("bad", policy))
