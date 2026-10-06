#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""VMware vCenter Orb worker Backend."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from netboxlabs.diode.sdk.ingester import Entity
from pydantic import ValidationError
from worker.backend import Backend
from worker.models import Metadata, Policy

from vmware_vcenter.client import InventoryClient, VCenterClient
from vmware_vcenter.map import map_devices
from vmware_vcenter.models import PolicyConfig, Scope

logger = logging.getLogger(__name__)

APP_NAME = "vmware-vcenter-worker"
APP_VERSION = "0.1.0"


class VMwareVCenterBackend(Backend):
    """Discover ESXi hosts from VMware vCenter (REST host inventory)."""

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
                for tests; defaults to constructing :class:`VCenterClient`.
            **kwargs: Forwarded to :class:`Backend`.

        """
        super().__init__(ingest_sink=ingest_sink, **kwargs)
        self._client_factory = client_factory or self._default_client_factory

    @classmethod
    def describe(cls) -> Metadata:
        """Return backend metadata without constructing an instance."""
        return Metadata(
            name="vmware_vcenter",
            app_name=APP_NAME,
            app_version=APP_VERSION,
            description="VMware vCenter ESXi host inventory discovery",
        )

    def run(self, policy_name: str, policy: Policy, **kwargs: Any) -> Iterable[Entity]:
        """Fetch vCenter host inventory and map it to Diode entities."""
        try:
            config = PolicyConfig(**policy.config.model_dump())
            if not isinstance(policy.scope, dict):
                raise ValueError("scope must be a mapping with host, username, and password")
            scope = Scope(**policy.scope)
        except (ValidationError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid vmware_vcenter policy '{policy_name}': {exc}") from exc

        # Never log passwords or full scope.
        logger.info(
            "Running policy '%s' against vCenter host=%s user=%s active_only=%s",
            policy_name,
            scope.host,
            scope.username,
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
            "Policy '%s' produced %d device entit(y/ies) from vCenter",
            policy_name,
            len(entities),
        )
        return entities

    @staticmethod
    def _default_client_factory(scope: Scope, config: PolicyConfig) -> InventoryClient:
        """Build the production vCenter HTTP client."""
        return VCenterClient(
            host=scope.host,
            username=scope.username,
            password=scope.password,
            verify_ssl=scope.verify_ssl,
            timeout=config.timeout,
        )
