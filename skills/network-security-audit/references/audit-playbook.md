# Audit playbook — step by step

The audit runs in seven phases. Each phase has an exit condition; do not enter
the next phase until the current one is satisfied or explicitly marked
`not checked`. Commands below are **read-only** and grouped per platform —
run only the block that matches the confirmed brand, and verify syntax against
official docs if a command is rejected (a rejected command is not a finding).

Phase order exists because later phases depend on earlier facts: you cannot
judge a firewall rule before you know which zone it faces, and you cannot
judge a CVE before you know the exact build.

---

## Phase 0 — Scope and authorization

Ask one compact question and record the answer:

```
Scope:        one device / a named set / every device in the inventory
Vantage:      local (device hardening) / perimeter (outside-in) / both
Active test:  allowed or not (a port scan from outside is active testing)
Window:       is there a maintenance-free constraint even for read-only work
```

Exit condition: you can write the scope line of the report.

Rules that bind the whole run:

- Read-only. No `set`, `configure`, `no`, `undo`, `write`, `save`, `commit`.
- Unreachable device → status `unknown`, never `secure`, never `pass`.
- Every finding carries verbatim evidence. No evidence → `not checked`.
- The audit never authorizes or vetoes a change. Findings only.

---

## Phase 1 — Establish identity, version, and reachability

Resolve the reference and confirm the device answers:

```bash
ntn list                       # inventory: hostname, ip:port, type, brand
ntn show <ref>                 # stored details + last snapshot
NTN_INTERNAL=1 ntn ping <ref>  # reachability before anything else
```

Identity commands per platform (pick one block):

| Platform | Command |
|---|---|
| Cisco IOS/IOS-XE | `show version` |
| MikroTik RouterOS | `/system resource print` + `/system routerboard print` |
| Huawei VRP | `display version` |
| HPE Aruba AOS-CX | `show version` |
| Arista EOS | `show version` |
| Juniper Junos | `show version` |
| Ruijie RGOS | `show version` |
| Fortinet FortiGate | `get system status` |
| Linux | `uname -a; cat /etc/os-release` |
| Windows | `systeminfo` |

Record exactly: vendor, product line, model, OS train, version, build/patch
level, uptime, and (where shown) license level. **Version is not patch
level** — build strings and release notes decide that, not the number shape.

Exit condition: exact platform identity in writing, plus reachability status.

If the device is unreachable: stop the device-specific phases, mark every
control `unknown`, write the report with that finding front and centre.

---

## Phase 2 — Management plane exposure

This is the most common real-world compromise path, so it comes before
routing or filtering.

Collect services and accounts:

| Platform | Commands |
|---|---|
| Cisco | `show ip http server status`, `show ip ssh`, `show running-config \| include ^(line vty\|transport input\|ip http\|snmp-server\|username\|enable secret\|service password)` |
| MikroTik | `/ip service print`, `/user print`, `/system ssh print`, `/ip ssh print` |
| Huawei | `display current-configuration \| include telnet\|ssh\|snmp\|aaa` |
| Aruba AOS-CX | `show running-config \| include ssh\|telnet\|snmp\|https-server` |
| Arista EOS | `show management api http-commands`, `show running-config \| include management\|snmp` |
| Juniper | `show configuration system services`, `show configuration snmp` |
| Ruijie | `show running-config \| include ssh\|telnet\|snmp` |
| Fortinet | `show system interface`, `show system admin`, `get system status` |
| Linux | `ss -lntup`, `systemctl list-units --type=service --state=running` |
| Windows | `Get-NetTCPConnection -State Listen`, `net user` |

Judge each control against `baselines.md` IDs `MGT-*`. For every listening
administrative service ask three questions:

1. Is it enabled at all? (telnet, ftp, http, api, snmp v1/v2c → CRIT if enabled)
2. Is it restricted to a management source range? (unrestricted → CRIT on a
   perimeter-facing device, WARN internally)
3. Is the credential path strong? (no enable secret / empty password /
   default account / password expiry disabled / unlimited session → WARN-CRIT)

Exit condition: a table of `service | state | source restriction | verdict`
with evidence lines.

---

## Phase 3 — Perimeter and forwarding

Determine what the device exposes to each trust zone and what it forwards.

```bash
# interfaces and zones first — you need to know which interface faces outside
```

| Platform | Commands |
|---|---|
| Cisco | `show ip interface brief`, `show running-config \| include ^interface\|ip address\|ip access-group\|nat` |
| MikroTik | `/interface print`, `/ip address print`, `/ip firewall filter print stats`, `/ip firewall nat print stats` |
| Huawei | `display ip interface brief`, `display acl all` |
| Aruba | `show ip interface brief`, `show access-list` |
| Arista | `show ip interface brief`, `show ip access-lists` |
| Juniper | `show interfaces terse`, `show firewall` |
| Ruijie | `show ip interface brief`, `show access-lists` |
| Fortinet | `get system interface physical`, `show firewall policy`, `get router info routing-table all` |

What to look for, in order of fatality:

- **No input filter at all on an outside-facing interface.** Everything the
  daemon listens on is reachable. CRIT.
- **A default-permit rule placed before the deny.** The policy looks present
  and is inert. Read rule order, not rule count. CRIT.
- **A permit rule with no source restriction** on a service you already found
  enabled in Phase 2. The combination is the finding, not either half.
- **NAT/port-forward exposing a management port** (22/23/80/443/8291/8728 to
  the device itself). CRIT.
- **No anti-spoofing** on an edge interface (BCP 38). WARN — and note the
  RFC, this is where spoofed traffic enters the internet.
- **RFC1918 accepted from the WAN side.** WARN unless the design explains it.

Rule counters are evidence of what the policy is *doing*, not what it says.
A deny rule with zero hits may be shadowed; a permit rule with millions of
hits tells you the exposure is live.

Exit condition: for each outside-facing interface, a stated
`default action`, `first matching rule for each exposed service`, and a
verdict. If the zone/role is ambiguous, ask — do not guess which side is
outside.

Perimeter honesty note: filter configuration shows *intended* policy. Measured
reachability needs an outside vantage point and explicit permission. If you did
not test actively, write `intended policy only — not measured` in the report.

---

## Phase 4 — Control plane and protocol hardening

| Control | Cisco | MikroTik | Huawei | Juniper |
|---|---|---|---|---|
| SSH version/crypto | `show ip ssh` | `/ip ssh print` | `display ssh server status` | `show configuration system services ssh` |
| SNMP version | `show snmp` | `/snmp print` | `display snmp-agent sys-info` | `show configuration snmp` |
| Logging target | `show logging` | `/system logging print` | `display logbuffer summary` | `show configuration system syslog` |
| NTP/time sync | `show ntp status` | `/system ntp client print` | `display ntp-service status` | `show configuration system ntp` |
| Routing auth | `show running-config \| include authentication` | `/routing ospf interface print` | `display ospf brief` | `show configuration protocols` |

Findings: SNMPv1/v2c with a default community (`public`/`private`) → CRIT.
SSHv1 enabled or weak KEX/ciphers offered → WARN. No log target, so an
incident leaves no trace → WARN. Time drifting (no NTP) → WARN, because every
timestamp in your evidence depends on it. Unauthenticated routing adjacencies
on an external-facing link → WARN.

Exit condition: each control marked `verified / not applicable / unknown`.

---

## Phase 5 — Change trail and drift

The stored snapshot is a claim; the live config is the fact.

```bash
NTN_INTERNAL=1 ntn audit pending    # attempts with no verdict at all
NTN_INTERNAL=1 ntn audit failed     # recorded failures
NTN_INTERNAL=1 ntn audit config 50  # device timeline
```

Full vocabulary and recovery: `network-troubleshooting` →
`references/audit-trail.md`.

Two distinct findings come out of this phase:

- **A change applied outside the approval gate** (config differs from the
  last recorded `config-ok` with no matching entry). Record the diff and the
  timestamp.
- **An unsettled apply** (a `config-pending` with no verdict). Device state is
  UNKNOWN. Pull a fresh snapshot and diff before trusting anything.

Exit condition: either "trail matches live config" or a written diff.

---

## Phase 6 — Version, lifecycle, and CVE research

Only now, because relevance needs the feature inventory you built in
Phases 2–4.

Follow `references/threat-research.md` exactly:

1. Exact product/model/build → supported or EOL, with the vendor lifecycle link.
2. Vendor PSIRT advisories for that version → then NVD/CVE.org to cross-check.
3. For each candidate CVE, test feature applicability against what you
   actually found enabled. An unused feature makes the CVE `INFO`, not `CRIT`.

Record per CVE: ID, CVSS, affected-version match, component/feature, whether
the device uses it, official link, research date.

Exit condition: every claim has a URL, or is written `not yet verified`.

---

## Phase 7 — Assemble and deliver

Use `templates/audit-report-template.md`. Fill every section, including
`Not checked` and `Limitations` — those two are what make the report
trustworthy rather than decorative.

Then stop. Do not execute remediation, do not schedule the next audit, do not
recommend a recurring cadence. Remediation is
`network-change-management`, and only after the user says go.

---

## Fleet runs

For more than one device: repeat Phases 1–6 per device, keep the evidence in
one file per device, and aggregate at the end.

- Never aggregate across an `unknown`. A fleet is not clean if one member was
  unreachable or one check went unverified.
- Report per-device counts, then a fleet total that explicitly names the
  devices excluded from it.
- Same finding on many devices → one finding entry with a device list, plus a
  note on whether the cause is shared (same template, same image, same
  operator habit).

---

## Quick reference — which skill owns what

| Situation | Skill |
|---|---|
| "Is this device secure?" | this playbook |
| "It's down / slow / flapping" | `network-troubleshooting` |
| "Change this setting" | `network-change-management` |
| "Add or remove a device" | `ntnroute` |
| "How do I SSH in manually" | `network-device-cli` |