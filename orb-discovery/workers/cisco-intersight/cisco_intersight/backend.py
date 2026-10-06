#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""Cisco Intersight Orb worker Backend."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from netboxlabs.diode.sdk.ingester import Entity
from pydantic import ValidationError
from worker.backend import Backend
from worker.models import Metadata, Policy

from cisco_intersight.client import InventoryClient, IntersightClient
from cisco_intersight.map import map_devices
from cisco_intersight.models import PolicyConfig, Scope

logger = logging.getLogger(__name__)

APP_NAME = "cisco-intersight-worker"
APP_VERSION = "0.1.0"


class CiscoIntersightBackend(Backend):
    """Discover compute endpoints from Cisco Intersight."""

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
                for tests; defaults to constructing :class:`IntersightClient`.
            **kwargs: Forwarded to :class:`Backend`.

        """
        super().__init__(ingest_sink=ingest_sink, **kwargs)
        self._client_factory = client_factory or self._default_client_factory

    @classmethod
    def describe(cls) -> Metadata:
        """Return backend metadata without constructing an instance."""
        return Metadata(
            name="cisco_intersight",
            app_name=APP_NAME,
            app_version=APP_VERSION,
            description="Cisco Intersight compute inventory discovery",
        )

    def run(self, policy_name: str, policy: Policy, **kwargs: Any) -> Iterable[Entity]:
        """Fetch Intersight inventory and map it to Diode entities."""
        try:
            config = PolicyConfig(**policy.config.model_dump())
            if not isinstance(policy.scope, dict):
                raise ValueError("scope must be a mapping with api_key_id and secret_key")
            scope = Scope(**policy.scope)
        except (ValidationError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid cisco_intersight policy '{policy_name}': {exc}") from exc

        # Never log secret keys or full scope.
        logger.info(
            "Running policy '%s' against Intersight host=%s active_only=%s",
            policy_name,
            scope.host,
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
            "Policy '%s' produced %d device entit(y/ies) from Intersight",
            policy_name,
            len(entities),
        )
        return entities

    @staticmethod
    def _default_client_factory(scope: Scope, config: PolicyConfig) -> InventoryClient:
        """Build the production Intersight HTTP client."""
        return IntersightClient(
            host=scope.host,
            api_key_id=scope.api_key_id,
            secret_key=scope.secret_key,
            verify_ssl=scope.verify_ssl,
            timeout=config.timeout,
        )
