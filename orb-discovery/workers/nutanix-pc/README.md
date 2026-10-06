# Nutanix Prism Central worker

Orb Agent worker package that discovers **clusters**, **physical hosts**, and
**virtual machines** from **Nutanix Prism Central** via the v3 list APIs, then
ingests them as Diode `Cluster`, `Device`, and `VirtualMachine` entities.

## Install into Orb Agent

This package ships in the agent image (baked from this repository). Enable the
`worker` backend and apply a policy with `package: nutanix_pc` — no
`INSTALL_WORKERS_PATH` mount is required.

```bash
docker run -v /local/orb:/opt/orb \
  -e DIODE_CLIENT_ID=... \
  -e DIODE_CLIENT_SECRET=... \
  -e PC_USERNAME=... \
  -e PC_PASSWORD=... \
  netboxlabs/orb-agent:latest run -c /opt/orb/agent.yaml
```

Use `INSTALL_WORKERS_PATH` only for custom/third-party worker packages, or to
override the baked package with a local checkout during development.

## Policy

```yaml
orb:
  backends:
    common:
      diode:
        target: grpc://diode:8080/diode
        client_id: ${DIODE_CLIENT_ID}
        client_secret: ${DIODE_CLIENT_SECRET}
        agent_name: nutanix-pc-agent
      otlp:
        grpc: localhost:4317   # enables orb-worker ops metrics
    worker:
  policies:
    worker:
      nutanix_pc_inventory:
        config:
          package: nutanix_pc
          schedule: "0 */6 * * *"
          active_only: true          # default; complete/online hosts and powered-on VMs
          timeout: 60                # HTTP timeout seconds
          defaults:
            site: dc1                # required
            role: hypervisor         # default: hypervisor
            manufacturer: Nutanix    # default: Nutanix
            platform: ahv            # default: ahv
            cluster_type: Nutanix AHV  # default
            vm_role: vm              # default: vm
            vm_platform: unknown     # default: unknown
            tags: ["nutanix-pc"]
        scope:
          host: https://pc.example.com:9440
          username: ${PC_USERNAME}
          password: ${PC_PASSWORD}
          verify_ssl: true           # set false for lab self-signed certs
```

### Config

| Field | Required | Description |
|-------|----------|-------------|
| `package` | yes | Must be `nutanix_pc` |
| `schedule` | no | Cron expression; omit to run once |
| `defaults.site` | yes | NetBox site for discovered objects |
| `defaults.role` | no | Device role for hosts (default `hypervisor`) |
| `defaults.manufacturer` | no | Manufacturer (default `Nutanix`) |
| `defaults.platform` | no | Platform for hosts (default `ahv`) |
| `defaults.cluster_type` | no | Cluster type (default `Nutanix AHV`) |
| `defaults.vm_role` | no | Role for VMs (default `vm`) |
| `defaults.vm_platform` | no | Platform for VMs (default `unknown`) |
| `defaults.tags` | no | Tags applied to each object |
| `active_only` | no | Only complete/online hosts and powered-on VMs (default `true`) |
| `timeout` | no | HTTP timeout in seconds (default `60`) |

### Scope

| Field | Required | Description |
|-------|----------|-------------|
| `host` | yes | Absolute Prism Central URL (`https://pc.example.com:9440`) |
| `username` | yes | Prism Central username |
| `password` | yes | Prism Central password (use `${PC_PASSWORD}` / vault) |
| `verify_ssl` | no | TLS verification (default `true`) |

Uses HTTP Basic authentication against the v3 list APIs. Passwords are never
written to logs.

Inventory endpoints:

- `POST /api/nutanix/v3/clusters/list` (`{"kind": "cluster"}`)
- `POST /api/nutanix/v3/hosts/list` (`{"kind": "host"}`)
- `POST /api/nutanix/v3/vms/list` (`{"kind": "vm"}`)

## What is discovered

### Clusters

| Prism Central field | Diode / NetBox |
|---------------------|----------------|
| `status.name` / `spec.name` | Cluster name |
| `status.state` | `active` or `offline` |
| policy `defaults.cluster_type` | Cluster type |
| policy `defaults.site` | Cluster scope site |

Cluster names referenced by hosts or VMs but missing from `clusters/list` are
still emitted so Device/VM references resolve.

### Hosts

| Prism Central field | Diode / NetBox |
|---------------------|----------------|
| `status.name` / `spec.name` | Device name |
| `resources.serial_number` (or host UUID) | Device serial |
| `resources.block_model_name` | Device type model |
| `resources.hypervisor_full_name` | Included in description |
| `resources.hypervisor_ip` | Primary IPv4 when dotted-quad; also in description |
| `status.state` | `active` or `offline` |
| `resources.cluster_name` | Device → Cluster |
| policy `defaults.*` | site, role, manufacturer, platform, tags |

### Virtual machines

| Prism Central field | Diode / NetBox |
|---------------------|----------------|
| `status.name` / `spec.name` | VirtualMachine name |
| `resources.power_state` | `active` (ON) or `offline` |
| `num_sockets` × `num_vcpus_per_socket` | vCPUs |
| `memory_size_mib` | Memory (MiB) |
| `disk_list` sizes | Disk (GiB) |
| `cluster_reference.name` | VirtualMachine → Cluster |
| `host_reference.name` | VirtualMachine → Device (host) |
| first NIC IPv4 | Primary IPv4 |
| policy `defaults.vm_role` / `vm_platform` | role, platform |

## Telemetry

- **Worker ops metrics** (policy runs, success/failure, latency) come from the
  shared `orb-worker` runtime when the agent configures `common.otlp.grpc`.
  This package does not implement its own OTEL exporter.
- **Device metrics** for Nutanix hosts use the agent `snmp_telemetry` backend
  with the bundled `nutanix/nutanix.yml` SNMP profile — not this discovery
  worker. There is no Prism Central API metrics collector today.

## Development

From this directory (with the sibling `orb-discovery/worker` package available):

```bash
pip install -e ../../worker
pip install -e ".[test]"
pytest
```
