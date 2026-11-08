# Hardening baseline — control catalog

A framework, not a parser or a pass/fail oracle. Each control has an ID so
findings and reports can reference it. For every control record one of:
`verified` (evidence collected, verdict given), `not applicable` (with the
reason), `not checked` (with the reason), `unknown` (device unreachable or
output unusable).

Applicability depends on model, OS/version, **role** (edge router, core
switch, access switch, CPE, lab box), and intended policy. A control that is
CRIT on an internet-facing edge is a WARN on an isolated lab segment. State
the role in the report before assigning severity.

---

## Management plane (MGT)

| ID | Control | Severity if failed |
|---|---|---|
| MGT-01 | No plaintext management protocol enabled (telnet, ftp, http, rsh). | CRIT |
| MGT-02 | Administrative services restricted to a management source range; not reachable from user or WAN zones. | CRIT on edge / WARN internal |
| MGT-03 | SSH enabled, v1 disabled, weak KEX/ciphers/HMACs removed, modern key exchange only. | WARN |
| MGT-04 | No default or blank credentials; a strong enable/privileged secret is set. | CRIT |
| MGT-05 | Least-privilege accounts: no shared admin, privilege levels appropriate, unused accounts removed. | WARN |
| MGT-06 | Session limits: exec-timeout set, vty/aux line access restricted with an ACL, max login attempts bounded. | WARN |
| MGT-07 | SNMP: v3 with auth+priv; v1/v2c denied or community strings non-default and ACL-restricted. | CRIT if v1/v2c default community |
| MGT-08 | Password/credential storage is hashed (type 8/9, `service-password-encryption`, etc.), not type 0/7/cleartext. | WARN |
| MGT-09 | Management access is isolated from the data plane (dedicated VRF/VLAN/mgmt port) where the role warrants it. | WARN |

## Perimeter and forwarding (PER)

| ID | Control | Severity if failed |
|---|---|---|
| PER-01 | Every outside-facing interface has an inbound filter; default action is deny. | CRIT |
| PER-02 | No default-permit rule positioned before the deny (check order, not count). | CRIT |
| PER-03 | Permit rules carry explicit source restrictions; no `permit any any` on a service found enabled. | CRIT |
| PER-04 | NAT/port-forward rules never expose a management port of the device itself. | CRIT |
| PER-05 | Anti-spoofing on edge interfaces (BCP 38 / RFC 2827+8704): no RFC1918 source from WAN, no own-prefix spoof. | WARN |
| PER-06 | Filter/NAT rules are observable: counters or logs enabled so the policy can be verified as live. | WARN |
| PER-07 | No shadowed/unreachable rules sitting where an operator believes they apply. | INFO-WARN |
| PER-08 | Routing protocols on external links are authenticated or explicitly trusted. | WARN |
| PER-09 | No unintended transit/forwarding between trust zones (device is not an accidental router). | CRIT if unintended |
| PER-10 | Outbound egress policy exists where the role requires it (not default-permit from user zones to anywhere). | INFO-WARN |

## Control plane and services (CTL)

| ID | Control | Severity if failed |
|---|---|---|
| CTL-01 | Discovery protocols scoped to intended links (CDP/LLDP/MNDP off on outside interfaces). | INFO-WARN |
| CTL-02 | Unused services disabled (proxy-arp, source routing, redirects, small servers, bootp, finger, web proxy). | WARN |
| CTL-03 | Logging to a remote collector; local buffer sized; timestamps correct. | WARN |
| CTL-04 | Time synchronization via authenticated NTP; clock drift bounded. | WARN |
| CTL-05 | Unused physical ports disabled and placed in an unused VLAN. | WARN (access) |
| CTL-06 | L2 protections where the role needs them: BPDU guard, root guard, DHCP snooping, dynamic ARP inspection, port security, storm control. | WARN, CRIT on access edge |
| CTL-07 | IPv6 handled deliberately — disabled, or filtered as carefully as IPv4. Unfiltered IPv6 alongside a hardened IPv4 stack is a bypass. | CRIT on edge |
| CTL-08 | Wireless/guest segmentation keeps guests off the management and corporate segments. | WARN-CRIT |

## Platform and operations (OPS)

| ID | Control | Severity if failed |
|---|---|---|
| OPS-01 | OS release is supported by the vendor (not EOL/end-of-support), link cited. | WARN-CRIT |
| OPS-02 | Security patches applied relative to the release's fixed-version advisories. | WARN-CRIT |
| OPS-03 | Configuration backed up, and the backup is current and restorable. | WARN |
| OPS-04 | Firmware/config change trail intact — no unexplained drift, no unsettled apply. | WARN |
| OPS-05 | Physical/environmental: console access protected, no exposed reset, adequate power/thermal margin if observable. | INFO |
| OPS-06 | No vendor default certificates/keys in use for management TLS. | WARN |

---

## Severity scale

- **CRIT** — a verified, reachable, high-impact exposure or a control that is
  simply absent where the role requires it, proven with evidence. It means
  "fix before this device carries production trust".
- **WARN** — a substantiated weakness that raises risk under stated
  conditions, or a control you could not verify on a device that should have it.
- **INFO** — context, improvement, or a CVE whose affected feature is not in
  use.

Severity is about the *device in its role*, not about how alarming the command
output looks. An exposed telnet port on a lab box that only you can reach is
still CRIT for the control, but say so with the reachability caveat attached.

## Rules for assigning a verdict

1. Evidence first. No command output → `not checked`, not `pass`.
2. Combination findings beat single ones. "Telnet enabled" is MGT-01; "telnet
   enabled and reachable from the WAN" is MGT-01 + MGT-02 + PER-03, and the
   combination is what gets exploited.
3. Feature applicability gates CVE severity. Unused feature → INFO with reason.
4. A missing control the vendor does not offer is `not applicable`, not a
   failure. Say which.
5. Never write "secure". Write "no findings against this baseline as of
   <date>, with these checks not performed: …".

## Reference material behind these controls

- RFC 3871 — BCP for securing IP networks (no telnet, AAA, logging, SNMP policy)
- BCP 38 (RFC 2827 / RFC 8704) — ingress anti-spoofing at the edge
- RFC 1918 — private ranges must not arrive from the WAN
- RFC 5246 / RFC 8446 — TLS 1.2/1.3; RC4/3DES/DES off
- NIST SP 800-53 (AC, IA, SC families) and CIS Benchmarks per platform —
  look up the current benchmark version at audit time
- Vendor hardening guides for the exact model and release

Verify every command and recommendation against official vendor documentation
for the platform you are auditing. No checklist is exhaustive, and this one is
deliberately platform-neutral.