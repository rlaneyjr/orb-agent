#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""Tests for AristaCVBackend policy handling."""

from unittest.mock import MagicMock

import pytest
from worker.backend import load_class
from worker.models import Config, Policy

from arista_cv.backend import APP_NAME, APP_VERSION, AristaCVBackend
from arista_cv.models import CVDevice


def _policy(**overrides) -> Policy:
    data = {
        "config": {
            "package": "arista_cv",
            "defaults": {
                "site": "dc1",
                "role": "network",
                "manufacturer": "Arista",
                "platform": "eos",
                "tags": ["cv"],
            },
        },
        "scope": {
            "host": "https://www.arista.io",
            "token": "test-token",
        },
    }
    data.update(overrides)
    return Policy(config=Config(**data["config"]), scope=data["scope"])


def test_describe():
    """describe returns stable metadata."""
    meta = AristaCVBackend.describe()
    assert meta.name == "arista_cv"
    assert meta.app_name == APP_NAME
    assert meta.app_version == APP_VERSION


def test_load_class_discovers_backend():
    """Worker load_class finds AristaCVBackend via package import."""
    assert load_class("arista_cv") is AristaCVBackend


def test_run_maps_devices_from_client():
    """run() uses the injected client and maps devices to entities."""
    mock_client = MagicMock()
    mock_client.list_devices.return_value = [
        CVDevice(
            device_id="SN1",
            hostname="leaf1",
            model_name="vEOS-lab",
            software_version="4.27.0F",
            streaming_status="STREAMING_STATUS_ACTIVE",
        )
    ]

    backend = AristaCVBackend(client_factory=lambda scope, config: mock_client)
    entities = list(backend.run("arista_cv_inventory", _policy()))

    mock_client.list_devices.assert_called_once_with(active_only=True)
    mock_client.close.assert_called_once()
    assert len(entities) == 1
    assert entities[0].device.name == "leaf1"
    assert entities[0].device.serial == "SN1"
    assert entities[0].device.site.name == "dc1"


def test_run_rejects_bad_package():
    """Wrong config.package fails validation."""
    backend = AristaCVBackend(client_factory=lambda *_: MagicMock())
    policy = _policy(
        config={
            "package": "other",
            "defaults": {"site": "dc1"},
        }
    )
    with pytest.raises(ValueError, match="Invalid arista_cv policy"):
        list(backend.run("bad", policy))


def test_run_rejects_non_mapping_scope():
    """Scope must be a mapping."""
    backend = AristaCVBackend(client_factory=lambda *_: MagicMock())
    policy = Policy(
        config=Config.model_validate(
            {
                "package": "arista_cv",
                "defaults": {"site": "dc1"},
            }
        ),
        scope=["not", "a", "map"],
    )
    with pytest.raises(ValueError, match="scope must be a mapping"):
        list(backend.run("bad", policy))


def test_run_rejects_missing_token():
    """Missing token fails scope validation."""
    backend = AristaCVBackend(client_factory=lambda *_: MagicMock())
    policy = _policy(scope={"host": "https://www.arista.io"})
    with pytest.raises(ValueError, match="Invalid arista_cv policy"):
        list(backend.run("bad", policy))


def test_run_rejects_relative_host():
    """Host must be an absolute URL."""
    backend = AristaCVBackend(client_factory=lambda *_: MagicMock())
    policy = _policy(scope={"host": "www.arista.io", "token": "t"})
    with pytest.raises(ValueError, match="Invalid arista_cv policy"):
        list(backend.run("bad", policy))
