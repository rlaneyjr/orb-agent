#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""Policy models for the A10 Control worker."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Defaults(BaseModel):
    """Default NetBox field values applied when A10 Control does not supply them."""

    model_config = ConfigDict(extra="forbid")

    site: str = Field(..., description="NetBox site name for discovered devices")
    role: str = Field(default="load-balancer", description="NetBox device role")
    manufacturer: str = Field(default="A10 Networks", description="NetBox manufacturer")
    platform: str = Field(default="acos", description="NetBox platform name")
    tags: list[str] = Field(default_factory=list, description="Tags applied to each device")


class PolicyConfig(BaseModel):
    """Validated worker policy config for a10_control."""

    model_config = ConfigDict(extra="allow")

    package: str = Field(..., description="Must be a10_control")
    schedule: str | None = Field(default=None, description="Optional cron schedule")
    defaults: Defaults
    timeout: float = Field(default=60.0, ge=1.0, description="HTTP timeout in seconds")
    active_only: bool = Field(
        default=True,
        description="When true, only ingest devices that appear connected/online",
    )

    @field_validator("package")
    @classmethod
    def package_must_be_a10_control(cls, value: str) -> str:
        """Require config.package to match this worker."""
        if value != "a10_control":
            raise ValueError("package must be 'a10_control'")
        return value


class Scope(BaseModel):
    """A10 Control connection scope."""

    model_config = ConfigDict(extra="forbid")

    host: str = Field(
        ...,
        description="A10 Control base URL, e.g. https://control.example.com",
    )
    api_key: str = Field(
        ...,
        min_length=1,
        description="Organization API key (Home → Organization pane)",
    )
    organization: str = Field(
        default="root",
        min_length=1,
        description="A10 Control organization name",
    )
    verify_ssl: bool = Field(
        default=True,
        description="Verify TLS certificates (set false for lab self-signed certs)",
    )

    @field_validator("host")
    @classmethod
    def normalize_host(cls, value: str) -> str:
        """Strip trailing slash and require an absolute http(s) URL."""
        host = value.strip().rstrip("/")
        if not host.startswith(("http://", "https://")):
            raise ValueError("host must be an absolute URL starting with http:// or https://")
        return host

    @field_validator("organization")
    @classmethod
    def normalize_organization(cls, value: str) -> str:
        """Strip whitespace from organization name."""
        organization = value.strip()
        if not organization:
            raise ValueError("organization must be a non-empty string")
        return organization


class A10Device(BaseModel):
    """Normalized A10 Control inventory device."""

    model_config = ConfigDict(extra="ignore")

    device_id: str
    hostname: str
    model_name: str | None = None
    software_version: str | None = None
    mgmt_ip: str | None = None
    serial: str | None = None
    status: str | None = None
    cluster_name: str | None = None
    cluster_id: str | None = None
