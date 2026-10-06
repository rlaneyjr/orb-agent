# VMware vCenter worker

Orb Agent worker package that discovers **ESXi hosts** from **VMware vCenter**
via the vSphere Automation REST API (`GET /api/vcenter/host`), then ingests them
as Diode `Device` entities.

## Future work

Guest VMs and vSphere clusters are deferred beyond this MVP. A follow-up should
emit Diode `Cluster` / `ClusterType` and `VirtualMachine` entities (and link
VM→host/cluster) for both this worker and the Nutanix Prism Central worker.

## Install into Orb Agent

Mount the package and point `INSTALL_WORKERS_PATH` at a `workers.txt` file:

```text
/local/orb/
├── agent.yaml
├── workers.txt
└── vmware-vcenter/          # this directory (contains pyproject.toml)
```

`workers.txt`:

```text
./vmware-vcenter
```

```bash
docker run -v /local/orb:/opt/orb \
  -e INSTALL_WORKERS_PATH=/opt/orb/workers.txt \
  -e DIODE_CLIENT_ID=... \
  -e DIODE_CLIENT_SECRET=... \
  -e VCENTER_USERNAME=... \
  -e VCENTER_PASSWORD=... \
  netboxlabs/orb-agent:latest run -c /opt/orb/agent.yaml
```

## Policy

```yaml
orb:
  backends:
    common:
      diode:
        target: grpc://diode:8080/diode
        client_id: ${DIODE_CLIENT_ID}
        client_secret: ${DIODE_CLIENT_SECRET}
        agent_name: vmware-vcenter-agent
      otlp:
        grpc: localhost:4317   # enables orb-worker ops metrics
    worker:
  policies:
    worker:
      vmware_vcenter_inventory:
        config:
          package: vmware_vcenter
          schedule: "0 */6 * * *"
          active_only: true          # default; only CONNECTED hosts
          timeout: 60                # HTTP timeout seconds
          defaults:
            site: dc1                # required
            role: hypervisor         # default: hypervisor
            manufacturer: VMware     # default: VMware
            platform: esxi           # default: esxi
            tags: ["vmware-vcenter"]
        scope:
          host: https://vcenter.example.com
          username: ${VCENTER_USERNAME}
          password: ${VCENTER_PASSWORD}
          verify_ssl: true           # set false for lab self-signed certs
```

### Config

| Field | Required | Description |
|-------|----------|-------------|
| `package` | yes | Must be `vmware_vcenter` |
| `schedule` | no | Cron expression; omit to run once |
| `defaults.site` | yes | NetBox site for discovered devices |
| `defaults.role` | no | Device role (default `hypervisor`) |
| `defaults.manufacturer` | no | Manufacturer (default `VMware`) |
| `defaults.platform` | no | Platform (default `esxi`) |
| `defaults.tags` | no | Tags applied to each device |
| `active_only` | no | Only CONNECTED hosts (default `true`) |
| `timeout` | no | HTTP timeout in seconds (default `60`) |

### Scope

| Field | Required | Description |
|-------|----------|-------------|
| `host` | yes | Absolute vCenter URL (`https://vcenter.example.com`) |
| `username` | yes | vCenter username |
| `password` | yes | vCenter password (use `${VCENTER_PASSWORD}` / vault) |
| `verify_ssl` | no | TLS verification (default `true`) |

Uses session authentication: `POST /api/session` (HTTP Basic) then
`vmware-api-session-id` on `GET /api/vcenter/host`. Passwords and session ids
are never written to logs.

## What is discovered (MVP)

| vCenter field | Diode / NetBox |
|---------------|----------------|
| `name` | Device name |
| `host` (MOID) | Device serial (Host.Summary has no hardware serial) |
| `connection_state` | `active` (CONNECTED) or `offline` |
| `power_state` | Included in description |
| policy `defaults.*` | site, role, manufacturer, platform, tags |

## Telemetry

- **Worker ops metrics** (policy runs, success/failure, latency) come from the
  shared `orb-worker` runtime when the agent configures `common.otlp.grpc`.
  This package does not implement its own OTEL exporter.
- **Device metrics** for VMware hosts can use the agent `snmp_telemetry` backend
  with bundled VMware SNMP profiles — not this discovery worker.

## Development

From this directory (with the sibling `orb-discovery/worker` package available):

```bash
pip install -e ../../worker
pip install -e ".[test]"
pytest
```
