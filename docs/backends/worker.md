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
./nutanix-pc # Nutanix Prism Central cluster/host/VM inventory worker
./cisco-intersight # Cisco Intersight compute inventory worker
./paloalto-panorama # Palo Alto Panorama managed-device inventory worker
./vmware-vcenter # VMware vCenter cluster/ESXi/VM inventory worker
```

### Telemetry for worker packages

First-party inventory workers do **not** collect device performance metrics from
controller APIs (CVaaS/CVP, A10 Control, Prism Central, Intersight, Panorama,
vCenter).

- **Worker ops metrics** (policy runs, success/failure, latency, API stats) are
  emitted by the shared `orb-worker` runtime when `common.otlp.grpc` is set on
  the agent — no per-package OTEL code is required.
- **Device metrics** use the agent `snmp_telemetry` / `gnmi_telemetry` backends
  with bundled vendor profiles (for example Arista switches, A10 Thunder,
  Nutanix, Palo Alto PAN-OS, VMware).

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

### Nutanix Prism Central

The first-party [`nutanix-pc`](../../orb-discovery/workers/nutanix-pc/README.md)
worker package discovers clusters, physical hosts, and VMs from Prism Central
(v3 list APIs) and ingests them via Diode. Install it with `INSTALL_WORKERS_PATH`
as above (add `./nutanix-pc` to `workers.txt`), then apply a policy:

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
      nutanix_pc_inventory:
        config:
          package: nutanix_pc
          schedule: "0 */6 * * *"
          defaults:
            site: dc1
            role: hypervisor
            manufacturer: Nutanix
            platform: ahv
            tags: ["nutanix-pc"]
        scope:
          host: https://pc.example.com:9440
          username: ${PC_USERNAME}
          password: ${PC_PASSWORD}
```

See the [package README](../../orb-discovery/workers/nutanix-pc/README.md) for the
full policy schema and Prism Central auth setup.

### Cisco Intersight

The first-party [`cisco-intersight`](../../orb-discovery/workers/cisco-intersight/README.md)
worker package discovers compute endpoints from Intersight and ingests them via
Diode. Install it with `INSTALL_WORKERS_PATH` as above (add `./cisco-intersight`
to `workers.txt`), then apply a policy:

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
      cisco_intersight_inventory:
        config:
          package: cisco_intersight
          schedule: "0 */6 * * *"
          defaults:
            site: dc1
            role: server
            manufacturer: Cisco
            platform: ucs
            tags: ["intersight"]
        scope:
          host: https://intersight.com
          api_key_id: ${INTERSIGHT_KEY_ID}
          secret_key: ${INTERSIGHT_SECRET_KEY}
```

See the [package README](../../orb-discovery/workers/cisco-intersight/README.md)
for the full policy schema and API-key signing setup.

### Palo Alto Panorama

The first-party [`paloalto-panorama`](../../orb-discovery/workers/paloalto-panorama/README.md)
worker package discovers managed firewalls from Panorama (`show devices all`) and
ingests them via Diode. Install it with `INSTALL_WORKERS_PATH` as above (add
`./paloalto-panorama` to `workers.txt`), then apply a policy:

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
      paloalto_panorama_inventory:
        config:
          package: paloalto_panorama
          schedule: "0 */6 * * *"
          defaults:
            site: dc1
            role: firewall
            manufacturer: Palo Alto Networks
            platform: panos
            tags: ["panorama"]
        scope:
          host: https://panorama.example.com
          api_key: ${PANORAMA_API_KEY}
```

See the [package README](../../orb-discovery/workers/paloalto-panorama/README.md)
for the full policy schema and XML API-key setup.

### VMware vCenter

The first-party [`vmware-vcenter`](../../orb-discovery/workers/vmware-vcenter/README.md)
worker package discovers clusters, ESXi hosts, and VMs from vCenter (REST
`/api/vcenter/cluster`, `/host`, `/vm`) and ingests them via Diode. Install it
with `INSTALL_WORKERS_PATH` as above (add `./vmware-vcenter` to `workers.txt`),
then apply a policy:

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
      vmware_vcenter_inventory:
        config:
          package: vmware_vcenter
          schedule: "0 */6 * * *"
          defaults:
            site: dc1
            role: hypervisor
            manufacturer: VMware
            platform: esxi
            tags: ["vmware-vcenter"]
        scope:
          host: https://vcenter.example.com
          username: ${VCENTER_USERNAME}
          password: ${VCENTER_PASSWORD}
```

See the [package README](../../orb-discovery/workers/vmware-vcenter/README.md) for
the full policy schema and vCenter session auth setup.
