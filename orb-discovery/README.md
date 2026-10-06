# orb-discovery

Orb discovery backends collection

- [device-discovery](./device-discovery/README.md) - Device Discovery Backend that uses [NAPALM](https://github.com/napalm-automation/napalm) Drivers.
- [network-discovery](./network-discovery/README.md) - Network Discovery Backend which is a wrapper over [NMAP](https://nmap.org/) scanner.
- [worker](./worker/README.md) - A Worker Backend that allows to run custom implementation as part of Orb Agent.
- [workers/arista-cv](./workers/arista-cv/README.md) - Worker package for Arista CloudVision (CVaaS / CVP) inventory discovery.
- [workers/a10-control](./workers/a10-control/README.md) - Worker package for A10 Control inventory discovery.
- [workers/nutanix-pc](./workers/nutanix-pc/README.md) - Worker package for Nutanix Prism Central cluster, host, and VM inventory discovery.
- [workers/cisco-intersight](./workers/cisco-intersight/README.md) - Worker package for Cisco Intersight compute inventory discovery.
- [workers/paloalto-panorama](./workers/paloalto-panorama/README.md) - Worker package for Palo Alto Panorama managed-device inventory discovery.
- [workers/vmware-vcenter](./workers/vmware-vcenter/README.md) - Worker package for VMware vCenter cluster, ESXi host, and VM inventory discovery.

### First-party workers (local install, no PyPI)

From the repo root:

```bash
make install-first-party-workers
source orb-discovery/workers/.venv/bin/activate
orb-worker -t 'grpc://...' -c "$DIODE_CLIENT_ID" -k "$DIODE_CLIENT_SECRET"
```

Or mount [workers/workers.txt](./workers/workers.txt) via `INSTALL_WORKERS_PATH` when running the agent container (see [docs/backends/worker.md](../docs/backends/worker.md)).
- [snmp-discovery](./snmp-discovery/README.md) - Device discovery that uses SNMP
- [gnmi-discovery](./gnmi-discovery/README.md) - Event-driven device discovery that uses [gNMI](https://github.com/openconfig/gnmi) subscriptions over [OpenConfig](https://www.openconfig.net/) models.