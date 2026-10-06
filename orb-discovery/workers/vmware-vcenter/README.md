# VMware vCenter worker

Orb Agent worker package that discovers **clusters**, **ESXi hosts**, and
**virtual machines** from **VMware vCenter** via the vSphere Automation REST API,
then ingests them as Diode `Cluster`, `Device`, and `VirtualMachine` entities.

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
          active_only: true          # default; CONNECTED hosts / POWERED_ON VMs
          timeout: 60                # HTTP timeout seconds
          defaults:
            site: dc1                # required
            role: hypervisor         # default: hypervisor
            manufacturer: VMware     # default: VMware
            platform: esxi           # default: esxi
            cluster_type: VMware vSphere  # default
            vm_role: vm              # default: vm
            vm_platform: unknown     # default: unknown
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
| `defaults.site` | yes | NetBox site for discovered objects |
| `defaults.role` | no | Device role for ESXi hosts (default `hypervisor`) |
| `defaults.manufacturer` | no | Manufacturer (default `VMware`) |
| `defaults.platform` | no | Platform for ESXi hosts (default `esxi`) |
| `defaults.cluster_type` | no | Cluster type (default `VMware vSphere`) |
| `defaults.vm_role` | no | Role for VMs (default `vm`) |
| `defaults.vm_platform` | no | Platform for VMs (default `unknown`) |
| `defaults.tags` | no | Tags applied to each object |
| `active_only` | no | Only CONNECTED hosts and POWERED_ON VMs (default `true`) |
| `timeout` | no | HTTP timeout in seconds (default `60`) |

### Scope

| Field | Required | Description |
|-------|----------|-------------|
| `host` | yes | Absolute vCenter URL (`https://vcenter.example.com`) |
| `username` | yes | vCenter username |
| `password` | yes | vCenter password (use `${VCENTER_PASSWORD}` / vault) |
| `verify_ssl` | no | TLS verification (default `true`) |

Uses session authentication: `POST /api/session` (HTTP Basic) then
`vmware-api-session-id` on inventory GETs. Passwords and session ids are never
written to logs.

Inventory endpoints:

- `GET /api/vcenter/cluster`
- `GET /api/vcenter/host` (with optional `?clusters=` for membership)
- `GET /api/vcenter/vm` (with optional `?clusters=` / `?hosts=` for linkage)

## What is discovered

### Clusters

| vCenter field | Diode / NetBox |
|---------------|----------------|
| `name` | Cluster name |
| policy `defaults.cluster_type` | Cluster type |
| policy `defaults.site` | Cluster scope site |
| `ha_enabled` / `drs_enabled` | Included in description |

### ESXi hosts

| vCenter field | Diode / NetBox |
|---------------|----------------|
| `name` | Device name |
| `host` (MOID) | Device serial (Host.Summary has no hardware serial) |
| `connection_state` | `active` (CONNECTED) or `offline` |
| `power_state` | Included in description |
| cluster membership | Device → Cluster |
| policy `defaults.*` | site, role, manufacturer, platform, tags |

### Virtual machines

| vCenter field | Diode / NetBox |
|---------------|----------------|
| `name` | VirtualMachine name |
| `power_state` | `active` (POWERED_ON) or `offline` |
| `cpu_count` | vCPUs |
| `memory_size_MiB` | Memory (MiB) |
| cluster filter | VirtualMachine → Cluster |
| host filter | VirtualMachine → Device (ESXi host) |
| policy `defaults.vm_role` / `vm_platform` | role, platform |

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
