# A10 Control worker

Orb Agent worker package that discovers devices from **A10 Control** (the
central management platform that consolidates Harmony Controller / aGalaxy)
via the organization ACAPI, then ingests them as Diode `Device` entities.

## Install into Orb Agent

This package ships in the agent image (baked from this repository). Enable the
`worker` backend and apply a policy with `package: a10_control` — no
`INSTALL_WORKERS_PATH` mount is required.

```bash
docker run -v /local/orb:/opt/orb \
  -e DIODE_CLIENT_ID=... \
  -e DIODE_CLIENT_SECRET=... \
  -e A10_API_KEY=... \
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
        agent_name: a10-control-agent
    worker:
  policies:
    worker:
      a10_control_inventory:
        config:
          package: a10_control
          schedule: "0 */6 * * *"
          active_only: true          # default; skip disconnected/offline devices
          timeout: 60                # HTTP timeout seconds
          defaults:
            site: dc1                # required
            role: load-balancer      # default: load-balancer
            manufacturer: A10 Networks  # default: A10 Networks
            platform: acos           # default: acos
            tags: ["a10-control"]
        scope:
          host: https://control.example.com
          api_key: ${A10_API_KEY}    # organization API key
          organization: root         # default: root
          verify_ssl: true           # set false for lab self-signed certs
```

### Config

| Field | Required | Description |
|-------|----------|-------------|
| `package` | yes | Must be `a10_control` |
| `schedule` | no | Cron expression; omit to run once |
| `defaults.site` | yes | NetBox site for discovered devices |
| `defaults.role` | no | Device role (default `load-balancer`) |
| `defaults.manufacturer` | no | Manufacturer (default `A10 Networks`) |
| `defaults.platform` | no | Platform (default `acos`) |
| `defaults.tags` | no | Tags applied to each device |
| `active_only` | no | Only connected/online devices (default `true`) |
| `timeout` | no | HTTP timeout in seconds (default `60`) |

### Scope

| Field | Required | Description |
|-------|----------|-------------|
| `host` | yes | Absolute A10 Control URL (`https://control.example.com`) |
| `api_key` | yes | Organization API key (use `${A10_API_KEY}` / vault) |
| `organization` | no | Organization name (default `root`) |
| `verify_ssl` | no | TLS verification (default `true`) |

Copy the organization API key from the A10 Control console as an
**Organization-Admin**: **Home → Organization** pane. See the
[A10 Control API Reference Guide](https://documentation.a10networks.com/SYM/Open_API/Latest/Index.html)
for authentication details. API keys are never written to logs.

## What is discovered (MVP)

| A10 Control field | Diode / NetBox |
|-------------------|----------------|
| `hostname` / `name` | Device name |
| `serial` (or `device-id`) | Device serial |
| `model` / `model-name` | Device type model |
| `software-version` / `version` | Included in description |
| `mgmt-ip` / `host` | Primary IPv4 when dotted-quad; also in description |
| `status` / connectivity | `active` or `offline` |
| `cluster-name` | Included in description |
| policy `defaults.*` | site, role, manufacturer, platform, tags |

The client calls
`GET /api/v2/acapi/v1/organization/{organization}/device/`. If that path is
unavailable, it falls back to `GET .../cluster/` and flattens embedded device
objects (or single-node cluster rows).

## Telemetry

- **Worker ops metrics** (policy runs, success/failure, latency) come from the
  shared `orb-worker` runtime when the agent configures `common.otlp.grpc`.
  This package does not implement its own OTEL exporter.
- **Device metrics** for A10 Thunder use `snmp_telemetry` with the bundled
  `a10_networks/a10-thunder.yml` profile — not this discovery worker. There is
  no A10 Control API metrics collector today.

## Development

From this directory (with the sibling `orb-discovery/worker` package available):

```bash
pip install -e ../../worker
pip install -e ".[test]"
pytest
```

Dry-run with a live A10 Control instance:

```bash
export A10_API_KEY=...
orb-worker -t 'grpc://diode:8080/diode' \
  -c '${DIODE_CLIENT_ID}' -k '${DIODE_CLIENT_SECRET}' \
  --dry-run -o /tmp/a10-control-dry-run
```

Then apply a worker policy that sets `package: a10_control` and your Control
`host` / `api_key` / `organization`.
