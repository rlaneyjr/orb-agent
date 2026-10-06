#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""A10 Control Orb worker Backend."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from netboxlabs.diode.sdk.ingester import Entity
from pydantic import ValidationError
from worker.backend import Backend
from worker.models import Metadata, Policy

from a10_control.client import A10ControlClient, InventoryClient
from a10_control.map import map_devices
from a10_control.models import PolicyConfig, Scope

logger = logging.getLogger(__name__)

APP_NAME = "a10-control-worker"
APP_VERSION = "0.1.0"


class A10ControlBackend(Backend):
    """Discover devices from A10 Control (organization ACAPI inventory)."""

    def __init__(
        self,
        *,
        ingest_sink: Any = None,
        client_factory: Any = None,
        **kwargs: Any,
    ) -> None:
        """
        Construct the backend.

        Args:
        ----
            ingest_sink: Optional worker ingest sink (forwarded to Backend).
            client_factory: Optional callable ``(scope, config) -> InventoryClient``
                for tests; defaults to constructing :class:`A10ControlClient`.
            **kwargs: Forwarded to :class:`Backend`.

        """
        super().__init__(ingest_sink=ingest_sink, **kwargs)
        self._client_factory = client_factory or self._default_client_factory

    @classmethod
    def describe(cls) -> Metadata:
        """Return backend metadata without constructing an instance."""
        return Metadata(
            name="a10_control",
            app_name=APP_NAME,
            app_version=APP_VERSION,
            description="A10 Control inventory discovery",
        )

    def run(self, policy_name: str, policy: Policy, **kwargs: Any) -> Iterable[Entity]:
        """Fetch A10 Control inventory and map it to Diode entities."""
        try:
            config = PolicyConfig(**policy.config.model_dump())
            if not isinstance(policy.scope, dict):
                raise ValueError("scope must be a mapping with host and api_key")
            scope = Scope(**policy.scope)
        except (ValidationError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid a10_control policy '{policy_name}': {exc}") from exc

        # Never log API keys or full scope.
        logger.info(
            "Running policy '%s' against A10 Control host=%s org=%s active_only=%s",
            policy_name,
            scope.host,
            scope.organization,
            config.active_only,
        )

        client = self._client_factory(scope, config)
        try:
            devices = client.list_devices(active_only=config.active_only)
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()

        entities = map_devices(devices, config.defaults)
        logger.info(
            "Policy '%s' produced %d device entit(y/ies) from A10 Control",
            policy_name,
            len(entities),
        )
        return entities

    @staticmethod
    def _default_client_factory(scope: Scope, config: PolicyConfig) -> InventoryClient:
        """Build the production A10 Control HTTP client."""
        return A10ControlClient(
            host=scope.host,
            api_key=scope.api_key,
            organization=scope.organization,
            verify_ssl=scope.verify_ssl,
            timeout=config.timeout,
        )
