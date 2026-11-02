# Per-brand diagnostic commands

All commands are **read-only**. Run them via `ntn exec <ref> '<cmd>'`.
The `ntn` engine already handles pagination, enable/secret, and session modes.

## Cisco IOS / IOS-XE

| Layer | Command | Purpose |
|---|---|---|
| L1 | `show interfaces` | Status of all interfaces, error counters, duplex |
| L1 | `show interfaces <name>` | Detail for one interface |
| L1 | `show controllers <name>` | Hardware statistics, CRC, overrun |
| L1 | `show interfaces status` | Ports, VLAN, duplex, speed (switch) |
| L2 | `show vlan brief` | VLAN membership (switch) |
| L2 | `show spanning-tree` | STP state, root bridge |
| L2 | `show cdp neighbors` | Layer-2 neighbors |
| L3 | `show ip interface brief` | IP summary of all interfaces |
| L3 | `show ip route` | Routing table |
| L3 | `show ip route <ip>` | Specific route lookup |
| L3 | `show ip arp` | ARP table |
| L3 | `show ip arp <ip>` | Specific ARP entry |
| L4 | `show access-lists` | ACL hit counters |
| L7 | `show ip http server status` | HTTP server status |
| General | `show logging` | Log buffer |
| General | `show version` | IOS version, uptime |
| General | `show processes cpu sorted` | CPU usage |
| General | `show processes memory sorted` | Memory usage |

## MikroTik RouterOS

| Layer | Command | Purpose |
|---|---|---|
| L1 | `/interface print detail` | Status of all interfaces, link-downs, MAC |
| L1 | `/interface ethernet print` | Ethernet only |
| L1 | `/interface ethernet monitor <name>` | Real-time link status (rate, duplex) |
| L2 | `/interface bridge print` | Bridge configuration |
| L2 | `/interface bridge host print` | Bridge MAC table |
| L2 | `/ip neighbor print` | LLDP/MNDP neighbors |
| L3 | `/ip address print` | IP addresses |
| L3 | `/ip route print` | Routing table |
| L3 | `/ip route check <ip>` | Verify the route to a destination |
| L3 | `/ip arp print` | ARP table |
| L3 | `/ping <ip>` | Ping from the device |
| L3 | `/traceroute <ip>` | Traceroute |
| L4 | `/ip firewall filter print` | Firewall rules |
| L4 | `/ip firewall connection print` | Active connections |
| L7 | `/ip dns print` | DNS settings |
| L7 | `/ip service print` | Services (ssh, www, api) |
| General | `/log print` | Log |
| General | `/system resource print` | CPU, memory, uptime |
| General | `/export` | Full config |
| General | `/tool torch` | Traffic monitoring (interactive) |
| General | `/tool ping <ip>` | Ping with extra options |

## Huawei VRP

| Layer | Command | Purpose |
|---|---|---|
| L1 | `display interface` | Status of all interfaces |
| L1 | `display interface <name>` | Detail for one interface |
| L1 | `display transceiver interface <name>` | SFP/optical info |
| L2 | `display vlan` | VLAN configuration |
| L2 | `display stp brief` | STP state |
| L2 | `display lldp neighbor brief` | LLDP neighbors |
| L3 | `display ip interface brief` | IP summary |
| L3 | `display ip routing-table` | Routing table |
| L3 | `display ip routing-table <ip>` | Route lookup |
| L3 | `display arp` | ARP table |
| L4 | `display acl all` | ACL rules + hits |
| General | `display logbuffer` | Log |
| General | `display version` | VRP version, uptime |
| General | `display cpu-usage` | CPU usage |
| General | `display memory-usage` | Memory usage |

## HPE Aruba AOS-CX

| Layer | Command | Purpose |
|---|---|---|
| L1 | `show interface` | Status of all interfaces |
| L1 | `show interface <name>` | Detail for one interface |
| L1 | `show transceiver detail` | SFP/optical info |
| L2 | `show vlan` | VLAN configuration |
| L2 | `show spanning-tree` | STP state |
| L2 | `show lldp neighbors-info` | LLDP neighbors |
| L3 | `show ip interface brief` | IP summary |
| L3 | `show ip route` | Routing table |
| L3 | `show arp` | ARP table |
| L4 | `show access-list` | ACL rules |
| General | `show logging` | Log |
| General | `show version` | Version, uptime |
| General | `show cpu` | CPU usage |
| General | `show memory` | Memory usage |

## Arista EOS

| Layer | Command | Purpose |
|---|---|---|
| L1 | `show interfaces` | Status of all interfaces |
| L1 | `show interfaces <name>` | Detail for one interface |
| L1 | `show interfaces transceiver` | SFP/optical info |
| L2 | `show vlan` | VLAN configuration |
| L2 | `show spanning-tree` | STP state |
| L2 | `show lldp neighbors` | LLDP neighbors |
| L3 | `show ip interface brief` | IP summary |
| L3 | `show ip route` | Routing table |
| L3 | `show ip route <ip>` | Route lookup |
| L3 | `show arp` | ARP table |
| L4 | `show access-lists` | ACL rules |
| General | `show logging` | Log |
| General | `show version` | Version, uptime |
| General | `show processes cpu` | CPU usage |
| General | `show processes memory` | Memory usage |

## Juniper Junos

| Layer | Command | Purpose |
|---|---|---|
| L1 | `show interfaces` | Status of all interfaces |
| L1 | `show interfaces <name>` | Detail for one interface |
| L1 | `show interfaces diagnostics optics <name>` | SFP/optical info |
| L2 | `show vlans` | VLAN configuration |
| L2 | `show spanning-tree interface` | STP state |
| L2 | `show lldp neighbors` | LLDP neighbors |
| L3 | `show interfaces terse` | IP summary |
| L3 | `show route` | Routing table |
| L3 | `show route <ip>` | Route lookup |
| L3 | `show arp` | ARP table |
| L4 | `show firewall` | Firewall rules |
| General | `show log messages` | Log |
| General | `show version` | Version, uptime |
| General | `show system processes summary` | CPU/memory |

## Ruijie RGOS

| Layer | Command | Purpose |
|---|---|---|
| L1 | `show interface` | Status of all interfaces |
| L1 | `show interface <name>` | Detail for one interface |
| L2 | `show vlan` | VLAN configuration |
| L2 | `show spanning-tree` | STP state |
| L2 | `show lldp neighbors` | LLDP neighbors |
| L3 | `show ip interface brief` | IP summary |
| L3 | `show ip routing-table` | Routing table |
| L3 | `show arp` | ARP table |
| L4 | `show access-lists` | ACL rules |
| General | `show logging` | Log |
| General | `show version` | Version, uptime |
| General | `show cpu` | CPU usage |
| General | `show memory` | Memory usage |

## Per-brand notes

- **MikroTik** has no `show` — every command starts with `/`. The `ntn` engine
  uses exec-mode (`ssh -T`); each line stands alone.
- **Huawei** uses `display` instead of `show`. Error patterns: `Error:`,
  `Unrecognized`, `Wrong parameter`.
- **Juniper** uses `show` but from `operational mode`. The engine already
  handles `set cli screen-length 0` for pagination.
- **Aruba AOS-CX** resembles Cisco but uses `show transceiver` instead of
  `show controllers`.
- **Ruijie** is very close to Cisco IOS — the `show` command set is nearly
  identical.
