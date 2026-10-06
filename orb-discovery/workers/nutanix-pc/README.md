# Nutanix Prism Central worker

Orb Agent worker package that discovers **physical hosts** from **Nutanix Prism
Central** via the v3 Hosts list API, then ingests them as Diode `Device`
entities. Guest VMs are deferred beyond this MVP.

## Install into Orb Agent

Mount the package and point `INSTALL_WORKERS_PATH` at a `workers.txt` file:

```text
/local/orb/
├── agent.yaml
├── workers.txt
└── nutanix-pc/          # this directory (contains pyproject.toml)
```

`workers.txt`:

```text
./nutanix-pc
```

```bash
docker run -v /local/orb:/opt/orb \
  -e INSTALL_WORKERS_PATH=/opt/orb/workers.txt \
  -e DIODE_CLIENT_ID=... \
  -e DIODE_CLIENT_SECRET=... \
  -e PC_USERNAME=... \
  -e PC_PASSWORD=... \
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
          active_only: true          # default; only COMPLETE/online hosts
          timeout: 60                # HTTP timeout seconds
          defaults:
            site: dc1                # required
            role: hypervisor         # default: hypervisor
            manufacturer: Nutanix    # default: Nutanix
            platform: ahv            # default: ahv
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
| `defaults.site` | yes | NetBox site for discovered devices |
| `defaults.role` | no | Device role (default `hypervisor`) |
| `defaults.manufacturer` | no | Manufacturer (default `Nutanix`) |
| `defaults.platform` | no | Platform (default `ahv`) |
| `defaults.tags` | no | Tags applied to each device |
| `active_only` | no | Only complete/online hosts (default `true`) |
| `timeout` | no | HTTP timeout in seconds (default `60`) |

### Scope

| Field | Required | Description |
|-------|----------|-------------|
| `host` | yes | Absolute Prism Central URL (`https://pc.example.com:9440`) |
| `username` | yes | Prism Central username |
| `password` | yes | Prism Central password (use `${PC_PASSWORD}` / vault) |
| `verify_ssl` | no | TLS verification (default `true`) |

Uses HTTP Basic authentication against
`POST /api/nutanix/v3/hosts/list`. Passwords are never written to logs.

## What is discovered (MVP)

| Prism Central field | Diode / NetBox |
|---------------------|----------------|
| `status.name` / `spec.name` | Device name |
| `resources.serial_number` (or host UUID) | Device serial |
| `resources.block_model_name` | Device type model |
| `resources.hypervisor_full_name` | Included in description |
| `resources.hypervisor_ip` | Primary IPv4 when dotted-quad; also in description |
| `status.state` | `active` or `offline` |
| `resources.cluster_name` | Included in description |
| policy `defaults.*` | site, role, manufacturer, platform, tags |

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
