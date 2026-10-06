#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""Policy models for the Nutanix Prism Central worker."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Defaults(BaseModel):
    """Default NetBox field values applied when Prism Central does not supply them."""

    model_config = ConfigDict(extra="forbid")

    site: str = Field(..., description="NetBox site name for discovered objects")
    role: str = Field(default="hypervisor", description="NetBox device role for AHV hosts")
    manufacturer: str = Field(default="Nutanix", description="NetBox manufacturer")
    platform: str = Field(default="ahv", description="NetBox platform name for AHV hosts")
    cluster_type: str = Field(
        default="Nutanix AHV",
        description="NetBox cluster type for discovered clusters",
    )
    vm_role: str = Field(default="vm", description="NetBox device role for virtual machines")
    vm_platform: str = Field(
        default="unknown",
        description="NetBox platform name for virtual machines when guest OS is unknown",
    )
    tags: list[str] = Field(default_factory=list, description="Tags applied to each object")


class PolicyConfig(BaseModel):
    """Validated worker policy config for nutanix_pc."""

    model_config = ConfigDict(extra="allow")

    package: str = Field(..., description="Must be nutanix_pc")
    schedule: str | None = Field(default=None, description="Optional cron schedule")
    defaults: Defaults
    timeout: float = Field(default=60.0, ge=1.0, description="HTTP timeout in seconds")
    active_only: bool = Field(
        default=True,
        description="When true, only ingest complete/online hosts and powered-on VMs",
    )

    @field_validator("package")
    @classmethod
    def package_must_be_nutanix_pc(cls, value: str) -> str:
        """Require config.package to match this worker."""
        if value != "nutanix_pc":
            raise ValueError("package must be 'nutanix_pc'")
        return value


class Scope(BaseModel):
    """Prism Central connection scope."""

    model_config = ConfigDict(extra="forbid")

    host: str = Field(
        ...,
        description="Prism Central base URL, e.g. https://pc.example.com:9440",
    )
    username: str = Field(..., min_length=1, description="Prism Central username")
    password: str = Field(..., min_length=1, description="Prism Central password")
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

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        """Strip whitespace from username."""
        username = value.strip()
        if not username:
            raise ValueError("username must be a non-empty string")
        return username


class ClusterInfo(BaseModel):
    """Normalized Prism Central cluster inventory record."""

    model_config = ConfigDict(extra="ignore")

    cluster_id: str
    name: str
    status: str | None = None


class PCHost(BaseModel):
    """Normalized Prism Central host inventory record."""

    model_config = ConfigDict(extra="ignore")

    device_id: str
    hostname: str
    model_name: str | None = None
    software_version: str | None = None
    mgmt_ip: str | None = None
    serial: str | None = None
    status: str | None = None
    cluster_name: str | None = None
    hypervisor: str | None = None


class GuestVM(BaseModel):
    """Normalized Prism Central virtual machine inventory record."""

    model_config = ConfigDict(extra="ignore")

    vm_id: str
    name: str
    power_state: str | None = None
    status: str | None = None
    cpu_count: int | None = None
    memory_mib: int | None = None
    disk_gb: int | None = None
    cluster_name: str | None = None
    host_name: str | None = None
    primary_ip: str | None = None
