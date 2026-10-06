#!/usr/bin/env python
# Copyright 2026 NetBox Labs Inc
"""Shared HTTP mock helpers for vCenter fixture inventory."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs

import httpx

from vmware_vcenter.client import CLUSTERS_PATH, HOSTS_PATH, SESSION_HEADER, SESSION_PATH, VMS_PATH

FIXTURES = Path(__file__).parent / "fixtures"
SESSION_ID = "test-session-id-not-a-secret"

_HOST_CLUSTER = {
    "domain-c21": {"host-11", "host-22"},
    "domain-c22": {"host-33"},
}
_VM_CLUSTER = {
    "domain-c21": {"vm-101", "vm-102"},
    "domain-c22": {"vm-199"},
}
_VM_HOST = {
    "host-11": {"vm-101"},
    "host-22": {"vm-102"},
    "host-33": {"vm-199"},
}


def fixture_json(name: str):
    """Load a JSON fixture by filename."""
    return json.loads((FIXTURES / name).read_text())


def fixture_text(name: str) -> str:
    """Load a fixture file as text."""
    return (FIXTURES / name).read_text()


def hosts_for_cluster(cluster_id: str | None) -> list[dict]:
    """Return host fixtures optionally filtered by cluster MOID."""
    hosts = fixture_json("hosts_list.json")
    if not cluster_id:
        return hosts
    allowed = _HOST_CLUSTER.get(cluster_id, set())
    return [h for h in hosts if h["host"] in allowed]


def vms_for_filter(*, cluster_id: str | None = None, host_id: str | None = None) -> list[dict]:
    """Return VM fixtures filtered by cluster or host MOID."""
    vms = fixture_json("vms_list.json")
    if cluster_id:
        allowed = _VM_CLUSTER.get(cluster_id, set())
        return [v for v in vms if v["vm"] in allowed]
    if host_id:
        allowed = _VM_HOST.get(host_id, set())
        return [v for v in vms if v["vm"] in allowed]
    return vms


def inventory_handler(request: httpx.Request, *, session_id: str = SESSION_ID) -> httpx.Response:
    """MockTransport handler covering session + cluster/host/VM inventory."""
    if request.url.path == SESSION_PATH:
        if request.method == "POST":
            return httpx.Response(200, json=session_id)
        if request.method == "DELETE":
            return httpx.Response(200)
        return httpx.Response(405)

    if request.headers.get(SESSION_HEADER) != session_id:
        return httpx.Response(401, text="missing session")

    params = parse_qs(request.url.query.decode() if isinstance(request.url.query, bytes) else request.url.query)
    cluster_id = (params.get("clusters") or [None])[0]
    host_id = (params.get("hosts") or [None])[0]

    routes = {
        CLUSTERS_PATH: lambda: httpx.Response(200, text=fixture_text("clusters_list.json")),
        HOSTS_PATH: lambda: httpx.Response(200, json=hosts_for_cluster(cluster_id)),
        VMS_PATH: lambda: httpx.Response(200, json=vms_for_filter(cluster_id=cluster_id, host_id=host_id)),
    }
    builder = routes.get(request.url.path)
    if builder is None or request.method != "GET":
        return httpx.Response(404)
    return builder()
