# Arista CloudVision worker

Orb Agent worker package that discovers devices from **Arista CloudVision as a
Service (CVaaS)** and **on-prem CloudVision Portal (CVP)** via the Inventory
Resource API, then ingests them as Diode `Device` entities.

## Install into Orb Agent

Mount the package and point `INSTALL_WORKERS_PATH` at a `workers.txt` file:

```text
/local/orb/
├── agent.yaml
├── workers.txt
└── arista-cv/          # this directory (contains pyproject.toml)
```

`workers.txt`:

```text
./arista-cv
```

```bash
docker run -v /local/orb:/opt/orb \
  -e INSTALL_WORKERS_PATH=/opt/orb/workers.txt \
  -e DIODE_CLIENT_ID=... \
  -e DIODE_CLIENT_SECRET=... \
  -e CV_TOKEN=... \
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
        agent_name: arista-cv-agent
    worker:
  policies:
    worker:
      arista_cv_inventory:
        config:
          package: arista_cv
          schedule: "0 */6 * * *"
          active_only: true          # default; only STREAMING_STATUS_ACTIVE
          timeout: 60                # HTTP timeout seconds
          defaults:
            site: dc1                # required
            role: network            # default: network
            manufacturer: Arista     # default: Arista
            platform: eos            # default: eos
            tags: ["cloudvision"]
        scope:
          host: https://www.arista.io   # or https://cvp.example.com
          token: ${CV_TOKEN}            # service account token
          verify_ssl: true              # set false for lab self-signed CVP certs
```

### Config

| Field | Required | Description |
|-------|----------|-------------|
| `package` | yes | Must be `arista_cv` |
| `schedule` | no | Cron expression; omit to run once |
| `defaults.site` | yes | NetBox site for discovered devices |
| `defaults.role` | no | Device role (default `network`) |
| `defaults.manufacturer` | no | Manufacturer (default `Arista`) |
| `defaults.platform` | no | Platform (default `eos`) |
| `defaults.tags` | no | Tags applied to each device |
| `active_only` | no | Only active streaming devices (default `true`) |
| `timeout` | no | HTTP timeout in seconds (default `60`) |

### Scope

| Field | Required | Description |
|-------|----------|-------------|
| `host` | yes | Absolute CloudVision URL (`https://www.arista.io` or CVP URL) |
| `token` | yes | Service account token (use `${CV_TOKEN}` / vault) |
| `verify_ssl` | no | TLS verification (default `true`) |

Create a service account token in CloudVision under **Settings → Access Control →
Service Accounts**. The same token auth works for CVaaS and on-prem CVP; only
`scope.host` changes.

## What is discovered (MVP)

| CloudVision field | Diode / NetBox |
|-------------------|----------------|
| `hostname` | Device name |
| `key.deviceId` | Device serial |
| `modelName` | Device type model |
| `softwareVersion` | Included in description |
| `streamingStatus` | `active` or `offline` |
| policy `defaults.*` | site, role, manufacturer, platform, tags |

## Development

From this directory (with the sibling `orb-discovery/worker` package available):

```bash
pip install -e ../../worker
pip install -e ".[test]"
pytest
```

Dry-run with a live CloudVision instance:

```bash
export CV_TOKEN=...
orb-worker -t 'grpc://diode:8080/diode' \
  -c '${DIODE_CLIENT_ID}' -k '${DIODE_CLIENT_SECRET}' \
  --dry-run -o /tmp/arista-cv-dry-run
```

Then apply a worker policy that sets `package: arista_cv` and your CVaaS/CVP
`host` / `token`. Tokens are never written to logs.
