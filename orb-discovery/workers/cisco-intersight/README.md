# Cisco Intersight worker

Orb Agent worker package that discovers **compute endpoints** from **Cisco
Intersight** (SaaS or on-prem appliance) via `GET /api/v1/compute/PhysicalSummaries`,
then ingests them as Diode `Device` entities.

## Install into Orb Agent

This package ships in the agent image (baked from this repository). Enable the
`worker` backend and apply a policy with `package: cisco_intersight` — no
`INSTALL_WORKERS_PATH` mount is required.

```bash
docker run -v /local/orb:/opt/orb \
  -e DIODE_CLIENT_ID=... \
  -e DIODE_CLIENT_SECRET=... \
  -e INTERSIGHT_KEY_ID=... \
  -e INTERSIGHT_SECRET_KEY=... \
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
        agent_name: intersight-agent
      otlp:
        grpc: localhost:4317   # enables orb-worker ops metrics
    worker:
  policies:
    worker:
      cisco_intersight_inventory:
        config:
          package: cisco_intersight
          schedule: "0 */6 * * *"
          active_only: true          # default; skip powered-off / absent
          timeout: 60
          defaults:
            site: dc1                # required
            role: server             # default: server
            manufacturer: Cisco      # default: Cisco
            platform: ucs            # default: ucs
            tags: ["intersight"]
        scope:
          host: https://intersight.com   # or https://intersight.example.com
          api_key_id: ${INTERSIGHT_KEY_ID}
          secret_key: ${INTERSIGHT_SECRET_KEY}  # PEM private key contents
          verify_ssl: true
```

### Config

| Field | Required | Description |
|-------|----------|-------------|
| `package` | yes | Must be `cisco_intersight` |
| `schedule` | no | Cron expression; omit to run once |
| `defaults.site` | yes | NetBox site for discovered devices |
| `defaults.role` | no | Device role (default `server`) |
| `defaults.manufacturer` | no | Manufacturer (default `Cisco`) |
| `defaults.platform` | no | Platform (default `ucs`) |
| `defaults.tags` | no | Tags applied to each device |
| `active_only` | no | Only powered-on / reachable (default `true`) |
| `timeout` | no | HTTP timeout in seconds (default `60`) |

### Scope

| Field | Required | Description |
|-------|----------|-------------|
| `host` | no | Absolute Intersight URL (default `https://intersight.com`) |
| `api_key_id` | yes | API key ID from Intersight |
| `secret_key` | yes | PEM secret key contents (use `${INTERSIGHT_SECRET_KEY}` / vault; `\n` escapes OK) |
| `verify_ssl` | no | TLS verification (default `true`) |

Create an API key under **Settings → API Keys** in Intersight. Each request is
signed with RSA-SHA256 HTTP signatures. Secret keys are never written to logs.

## What is discovered (MVP)

| Intersight field | Diode / NetBox |
|------------------|----------------|
| `Name` | Device name |
| `Serial` (or `Moid`) | Device serial |
| `Model` | Device type model |
| `Firmware` | Included in description |
| `MgmtIpAddress` | Primary IPv4 when dotted-quad; also in description |
| `OperPowerState` | `active` or `offline` |
| policy `defaults.*` | site, role, manufacturer, platform, tags |

## Telemetry

- **Worker ops metrics** come from the shared `orb-worker` runtime when the
  agent configures `common.otlp.grpc`. This package does not implement its own
  OTEL exporter.
- **Device metrics** for UCS / Cisco gear use `snmp_telemetry` or
  `gnmi_telemetry` with vendor profiles — not this discovery worker. There is
  no Intersight API metrics collector today.

## Development

```bash
pip install -e ../../worker
pip install -e ".[test]"
pytest
```
