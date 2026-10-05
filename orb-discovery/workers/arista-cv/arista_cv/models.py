#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""Policy models for the Arista CloudVision worker."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Defaults(BaseModel):
    """Default NetBox field values applied when CloudVision does not supply them."""

    model_config = ConfigDict(extra="forbid")

    site: str = Field(..., description="NetBox site name for discovered devices")
    role: str = Field(default="network", description="NetBox device role")
    manufacturer: str = Field(default="Arista", description="NetBox manufacturer")
    platform: str = Field(default="eos", description="NetBox platform name")
    tags: list[str] = Field(default_factory=list, description="Tags applied to each device")


class PolicyConfig(BaseModel):
    """Validated worker policy config for arista_cv."""

    model_config = ConfigDict(extra="allow")

    package: str = Field(..., description="Must be arista_cv")
    schedule: str | None = Field(default=None, description="Optional cron schedule")
    defaults: Defaults
    timeout: float = Field(default=60.0, ge=1.0, description="HTTP timeout in seconds")
    active_only: bool = Field(
        default=True,
        description="When true, only ingest devices with STREAMING_STATUS_ACTIVE",
    )

    @field_validator("package")
    @classmethod
    def package_must_be_arista_cv(cls, value: str) -> str:
        """Require config.package to match this worker."""
        if value != "arista_cv":
            raise ValueError("package must be 'arista_cv'")
        return value


class Scope(BaseModel):
    """CloudVision connection scope."""

    model_config = ConfigDict(extra="forbid")

    host: str = Field(
        ...,
        description="CloudVision base URL, e.g. https://www.arista.io or https://cvp.example.com",
    )
    token: str = Field(..., min_length=1, description="Service account token")
    verify_ssl: bool = Field(
        default=True,
        description="Verify TLS certificates (set false for lab CVP with self-signed certs)",
    )

    @field_validator("host")
    @classmethod
    def normalize_host(cls, value: str) -> str:
        """Strip trailing slash and require an absolute http(s) URL."""
        host = value.strip().rstrip("/")
        if not host.startswith(("http://", "https://")):
            raise ValueError("host must be an absolute URL starting with http:// or https://")
        return host


class CVDevice(BaseModel):
    """Normalized CloudVision inventory device."""

    model_config = ConfigDict(extra="ignore")

    device_id: str
    hostname: str
    model_name: str | None = None
    software_version: str | None = None
    fqdn: str | None = None
    system_mac_address: str | None = None
    streaming_status: str | None = None
    hardware_revision: str | None = None
    domain_name: str | None = None
