#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""Policy models for the Cisco Intersight worker."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Defaults(BaseModel):
    """Default NetBox field values applied when Intersight does not supply them."""

    model_config = ConfigDict(extra="forbid")

    site: str = Field(..., description="NetBox site name for discovered devices")
    role: str = Field(default="server", description="NetBox device role")
    manufacturer: str = Field(default="Cisco", description="NetBox manufacturer")
    platform: str = Field(default="ucs", description="NetBox platform name")
    tags: list[str] = Field(default_factory=list, description="Tags applied to each device")


class PolicyConfig(BaseModel):
    """Validated worker policy config for cisco_intersight."""

    model_config = ConfigDict(extra="allow")

    package: str = Field(..., description="Must be cisco_intersight")
    schedule: str | None = Field(default=None, description="Optional cron schedule")
    defaults: Defaults
    timeout: float = Field(default=60.0, ge=1.0, description="HTTP timeout in seconds")
    active_only: bool = Field(
        default=True,
        description="When true, only ingest endpoints that appear powered on / reachable",
    )

    @field_validator("package")
    @classmethod
    def package_must_be_cisco_intersight(cls, value: str) -> str:
        """Require config.package to match this worker."""
        if value != "cisco_intersight":
            raise ValueError("package must be 'cisco_intersight'")
        return value


class Scope(BaseModel):
    """Intersight connection scope."""

    model_config = ConfigDict(extra="forbid")

    host: str = Field(
        default="https://intersight.com",
        description="Intersight base URL (SaaS or appliance)",
    )
    api_key_id: str = Field(..., min_length=1, description="Intersight API key ID")
    secret_key: str = Field(
        ...,
        min_length=1,
        description="Intersight API secret key PEM (private key contents)",
    )
    verify_ssl: bool = Field(
        default=True,
        description="Verify TLS certificates (set false for lab appliance certs)",
    )

    @field_validator("host")
    @classmethod
    def normalize_host(cls, value: str) -> str:
        """Strip trailing slash and require an absolute http(s) URL."""
        host = value.strip().rstrip("/")
        if not host.startswith(("http://", "https://")):
            raise ValueError("host must be an absolute URL starting with http:// or https://")
        return host

    @field_validator("api_key_id")
    @classmethod
    def normalize_api_key_id(cls, value: str) -> str:
        """Strip whitespace from API key ID."""
        key_id = value.strip()
        if not key_id:
            raise ValueError("api_key_id must be a non-empty string")
        return key_id

    @field_validator("secret_key")
    @classmethod
    def normalize_secret_key(cls, value: str) -> str:
        """Normalize escaped newlines often seen when PEMs are stored in env vars."""
        secret = value.strip().replace("\\n", "\n")
        if not secret:
            raise ValueError("secret_key must be a non-empty PEM string")
        return secret


class IntersightDevice(BaseModel):
    """Normalized Intersight compute inventory record."""

    model_config = ConfigDict(extra="ignore")

    device_id: str
    hostname: str
    model_name: str | None = None
    software_version: str | None = None
    mgmt_ip: str | None = None
    serial: str | None = None
    status: str | None = None
    vendor: str | None = None
