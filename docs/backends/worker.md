# Worker
The worker backend allows to run custom implementation as part of Orb Agent.

## Diode Entities
The worker backend can ingest any [supported entity](https://github.com/netboxlabs/diode-sdk-python?tab=readme-ov-file#supported-entities-object-types) of Diode Python SDK.

## Configuration
The `worker` backend does not require any special configuration, though overriding `host` and `port` values can be specified. The backend will use the `diode` settings specified in the `common` subsection to forward discovery results.

```yaml
orb:
  backends:
    common:
      diode:
        target: grpc://192.168.0.100:8080/diode
        client_id: ${DIODE_CLIENT_ID}
        client_secret: ${DIODE_CLIENT_SECRET}
        agent_name: agent01
    worker:
      host: 192.168.5.11 # default 0.0.0.0
      port: 8857 # default 8071

```

## Policy
Worker policies are broken down into two subsections: `config` and `scope`. 

### Config
Config defines data for the whole scope and is optional overall.

| Parameter | Type | Required | Description |
|:---------:|:----:|:--------:|:-----------:|
| package | str | yes  |  custom python package that implements Backend Class  |
| schedule | cron format | no  |  If defined, it will execute scope following cron schedule time. If not defined, it will execute scope only once  |


### Scope
The scope can be defined as either a `list` or a `map`, allowing the user to parse it according to their preference.

### Sample
A sample policy including all parameters supported by the device discovery backend.
```yaml
orb:
  ...
  policies:
    worker:
      custom_policy:
        config:
          package: nbl_custom
          schedule: "* * * * *"
          custom_config: custom
        scope:
          custom: any
```

### Custom Workers
To specify required custom workers packages, use the environment variable `INSTALL_WORKERS_PATH`. Ensure that the required files are placed in the mounted volume (`/opt/orb`).

Mounted folder example:
```sh
/local/orb/
├── agent.yaml
├── workers.txt
├── my-worker/
└── nbl-custom-worker-1.0.2.tar.gz
```

Example `workers.txt`:
```txt
my-custom-wkr==0.1.2 # try install from pypi
nbl-custom-worker-1.0.2.tar.gz # try install from a tar.gz
./my-worker # try to install from a folder that contains project.toml
./arista-cv # Arista CloudVision (CVaaS/CVP) inventory worker
./a10-control # A10 Control inventory worker
```

### Arista CloudVision (CVaaS / CVP)

The first-party [`arista-cv`](../../orb-discovery/workers/arista-cv/README.md)
worker package discovers devices from CloudVision inventory and ingests them via
Diode. Install it with `INSTALL_WORKERS_PATH` as above (add `./arista-cv` to
`workers.txt`), then apply a policy:

```yaml
orb:
  backends:
    common:
      diode:
        target: grpc://192.168.0.100:8080/diode
        client_id: ${DIODE_CLIENT_ID}
        client_secret: ${DIODE_CLIENT_SECRET}
        agent_name: agent01
    worker:
  policies:
    worker:
      arista_cv_inventory:
        config:
          package: arista_cv
          schedule: "0 */6 * * *"
          defaults:
            site: dc1
            role: network
            manufacturer: Arista
            platform: eos
            tags: ["cloudvision"]
        scope:
          host: https://www.arista.io   # or https://cvp.example.com
          token: ${CV_TOKEN}
```

See the [package README](../../orb-discovery/workers/arista-cv/README.md) for the
full policy schema and service-account token setup.

### A10 Control

The first-party [`a10-control`](../../orb-discovery/workers/a10-control/README.md)
worker package discovers Thunder devices from A10 Control inventory and ingests
them via Diode. Install it with `INSTALL_WORKERS_PATH` as above (add
`./a10-control` to `workers.txt`), then apply a policy:

```yaml
orb:
  backends:
    common:
      diode:
        target: grpc://192.168.0.100:8080/diode
        client_id: ${DIODE_CLIENT_ID}
        client_secret: ${DIODE_CLIENT_SECRET}
        agent_name: agent01
    worker:
  policies:
    worker:
      a10_control_inventory:
        config:
          package: a10_control
          schedule: "0 */6 * * *"
          defaults:
            site: dc1
            role: load-balancer
            manufacturer: A10 Networks
            platform: acos
            tags: ["a10-control"]
        scope:
          host: https://control.example.com
          api_key: ${A10_API_KEY}
          organization: root
```

See the [package README](../../orb-discovery/workers/a10-control/README.md) for the
full policy schema and organization API-key setup.
