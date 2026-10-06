#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""Policy models for the Palo Alto Panorama worker."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Defaults(BaseModel):
    """Default NetBox field values applied when Panorama does not supply them."""

    model_config = ConfigDict(extra="forbid")

    site: str = Field(..., description="NetBox site name for discovered devices")
    role: str = Field(default="firewall", description="NetBox device role")
    manufacturer: str = Field(default="Palo Alto Networks", description="NetBox manufacturer")
    platform: str = Field(default="panos", description="NetBox platform name")
    tags: list[str] = Field(default_factory=list, description="Tags applied to each device")


class PolicyConfig(BaseModel):
    """Validated worker policy config for paloalto_panorama."""

    model_config = ConfigDict(extra="allow")

    package: str = Field(..., description="Must be paloalto_panorama")
    schedule: str | None = Field(default=None, description="Optional cron schedule")
    defaults: Defaults
    timeout: float = Field(default=60.0, ge=1.0, description="HTTP timeout in seconds")
    active_only: bool = Field(
        default=True,
        description="When true, only ingest devices that report connected=yes",
    )

    @field_validator("package")
    @classmethod
    def package_must_be_paloalto_panorama(cls, value: str) -> str:
        """Require config.package to match this worker."""
        if value != "paloalto_panorama":
            raise ValueError("package must be 'paloalto_panorama'")
        return value


class Scope(BaseModel):
    """Panorama connection scope."""

    model_config = ConfigDict(extra="forbid")

    host: str = Field(
        ...,
        description="Panorama base URL, e.g. https://panorama.example.com",
    )
    api_key: str = Field(..., min_length=1, description="Panorama XML API key")
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


class PanoramaDevice(BaseModel):
    """Normalized Panorama managed-device inventory record."""

    model_config = ConfigDict(extra="ignore")

    device_id: str
    hostname: str
    model_name: str | None = None
    software_version: str | None = None
    mgmt_ip: str | None = None
    serial: str | None = None
    status: str | None = None
    device_group: str | None = None
    vsys: str | None = None
