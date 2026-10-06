# Palo Alto Panorama worker

Orb Agent worker package that discovers **managed firewalls** from **Palo Alto
Panorama** via the XML operational API (`show devices all`), then ingests them
as Diode `Device` entities.

## Install into Orb Agent

Mount the package and point `INSTALL_WORKERS_PATH` at a `workers.txt` file:

```text
/local/orb/
├── agent.yaml
├── workers.txt
└── paloalto-panorama/          # this directory (contains pyproject.toml)
```

`workers.txt`:

```text
./paloalto-panorama
```

```bash
docker run -v /local/orb:/opt/orb \
  -e INSTALL_WORKERS_PATH=/opt/orb/workers.txt \
  -e DIODE_CLIENT_ID=... \
  -e DIODE_CLIENT_SECRET=... \
  -e PANORAMA_API_KEY=... \
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
        agent_name: panorama-agent
      otlp:
        grpc: localhost:4317   # enables orb-worker ops metrics
    worker:
  policies:
    worker:
      paloalto_panorama_inventory:
        config:
          package: paloalto_panorama
          schedule: "0 */6 * * *"
          active_only: true          # default; only connected=yes
          timeout: 60
          defaults:
            site: dc1                # required
            role: firewall           # default: firewall
            manufacturer: Palo Alto Networks
            platform: panos          # default: panos
            tags: ["panorama"]
        scope:
          host: https://panorama.example.com
          api_key: ${PANORAMA_API_KEY}
          verify_ssl: true
```

### Config

| Field | Required | Description |
|-------|----------|-------------|
| `package` | yes | Must be `paloalto_panorama` |
| `schedule` | no | Cron expression; omit to run once |
| `defaults.site` | yes | NetBox site for discovered devices |
| `defaults.role` | no | Device role (default `firewall`) |
| `defaults.manufacturer` | no | Manufacturer (default `Palo Alto Networks`) |
| `defaults.platform` | no | Platform (default `panos`) |
| `defaults.tags` | no | Tags applied to each device |
| `active_only` | no | Only connected devices (default `true`) |
| `timeout` | no | HTTP timeout in seconds (default `60`) |

### Scope

| Field | Required | Description |
|-------|----------|-------------|
| `host` | yes | Absolute Panorama URL |
| `api_key` | yes | XML API key (use `${PANORAMA_API_KEY}` / vault) |
| `verify_ssl` | no | TLS verification (default `true`) |

Generate an API key with `type=keygen` (or via the Panorama UI). Requests use
the `X-PAN-KEY` header. API keys are never written to logs.

## What is discovered (MVP)

| Panorama field | Diode / NetBox |
|----------------|----------------|
| `hostname` | Device name |
| `serial` | Device serial |
| `model` | Device type model |
| `sw-version` | Included in description |
| `ip-address` | Primary IPv4 when dotted-quad; also in description |
| `connected` | `active` or `offline` |
| `device-group` | Included in description |
| policy `defaults.*` | site, role, manufacturer, platform, tags |

## Telemetry

- **Worker ops metrics** come from the shared `orb-worker` runtime when the
  agent configures `common.otlp.grpc`. This package does not implement its own
  OTEL exporter.
- **Device metrics** for PAN-OS firewalls use `snmp_telemetry` with the
  bundled `palo_alto/palo-alto.yml` profile — not this discovery worker. There
  is no Panorama API metrics collector today.

## Development

```bash
pip install -e ../../worker
pip install -e ".[test]"
pytest
```
