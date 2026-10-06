#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""Policy models for the VMware vCenter worker."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Defaults(BaseModel):
    """Default NetBox field values applied when vCenter does not supply them."""

    model_config = ConfigDict(extra="forbid")

    site: str = Field(..., description="NetBox site name for discovered objects")
    role: str = Field(default="hypervisor", description="NetBox device role for ESXi hosts")
    manufacturer: str = Field(default="VMware", description="NetBox manufacturer")
    platform: str = Field(default="esxi", description="NetBox platform name for ESXi hosts")
    cluster_type: str = Field(
        default="VMware vSphere",
        description="NetBox cluster type for discovered clusters",
    )
    vm_role: str = Field(default="vm", description="NetBox device role for virtual machines")
    vm_platform: str = Field(
        default="unknown",
        description="NetBox platform name for virtual machines when guest OS is unknown",
    )
    tags: list[str] = Field(default_factory=list, description="Tags applied to each object")


class PolicyConfig(BaseModel):
    """Validated worker policy config for vmware_vcenter."""

    model_config = ConfigDict(extra="allow")

    package: str = Field(..., description="Must be vmware_vcenter")
    schedule: str | None = Field(default=None, description="Optional cron schedule")
    defaults: Defaults
    timeout: float = Field(default=60.0, ge=1.0, description="HTTP timeout in seconds")
    active_only: bool = Field(
        default=True,
        description="When true, only ingest CONNECTED hosts and POWERED_ON VMs",
    )

    @field_validator("package")
    @classmethod
    def package_must_be_vmware_vcenter(cls, value: str) -> str:
        """Require config.package to match this worker."""
        if value != "vmware_vcenter":
            raise ValueError("package must be 'vmware_vcenter'")
        return value


class Scope(BaseModel):
    """vCenter connection scope."""

    model_config = ConfigDict(extra="forbid")

    host: str = Field(
        ...,
        description="vCenter base URL, e.g. https://vcenter.example.com",
    )
    username: str = Field(..., min_length=1, description="vCenter username")
    password: str = Field(..., min_length=1, description="vCenter password")
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
    """Normalized vCenter cluster inventory record."""

    model_config = ConfigDict(extra="ignore")

    cluster_id: str
    name: str
    ha_enabled: bool | None = None
    drs_enabled: bool | None = None


class ESXiHost(BaseModel):
    """Normalized vCenter ESXi host inventory record."""

    model_config = ConfigDict(extra="ignore")

    device_id: str
    hostname: str
    model_name: str | None = None
    software_version: str | None = None
    mgmt_ip: str | None = None
    serial: str | None = None
    status: str | None = None
    power_state: str | None = None
    cluster_name: str | None = None


class GuestVM(BaseModel):
    """Normalized vCenter virtual machine inventory record."""

    model_config = ConfigDict(extra="ignore")

    vm_id: str
    name: str
    power_state: str | None = None
    cpu_count: int | None = None
    memory_mib: int | None = None
    cluster_name: str | None = None
    host_name: str | None = None
