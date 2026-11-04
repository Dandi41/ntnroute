---
name: network-troubleshooting
description: "OSI-first network device diagnosis with vendor commands."
version: 1.0.0
author: Dandi Suryadi, Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [network, troubleshooting, cisco, mikrotik, huawei, aruba, arista, juniper, ruijie, osi, diagnosis]
    related_skills: [ntnroute, network-device-cli, network-change-management, network-security-audit]
---

# Network Troubleshooting

Network device diagnosis using the OSI layer principle, backed by the `ntn`
engine and the `triage` script that reads `show` output without touching
the device.

## When to Use

- A device in the `ntn` inventory is unreachable, slow, or behaving oddly.
- A user reports "no internet", "can't ping", "link down", "duplex errors".
- You need to read the real state before deciding on a configuration change.
- You need to distinguish: device down vs path down vs your own SSH session dying.

Not for: changing configuration (that is the `network-change-management` skill),
adding/removing devices (that is the `ntnroute` skill), or plain Linux servers.

## Core Principles

1. **OSI layers, don't skip.** L1 → L2 → L3 → L4 → L7. Prove the lower layer
   is healthy before moving up. Exception: a specific symptom (DNS timeout) may
   go straight to the relevant layer.
2. **Read-only first.** All diagnostic commands are read-only. No
   `configure`, `set`, or `remove` during diagnosis. Changes = the
   `network-change-management` skill.
3. **One symptom = one hypothesis.** Every hypothesis needs a command that
   proves it. No "try restarting" without evidence.
4. **Absolute counters mean nothing.** Read error counters twice with a pause
   between reads; what matters is a number that is **climbing**.
5. **Record findings.** What was checked, key output, conclusion. Without
   notes, the same checks get repeated.
6. **A falsified hypothesis gets discarded.** Don't patch an old hypothesis to
   fit the evidence.

## Diagnosis Procedure

### 1. Define the scope

Ask the user: which device, what symptom, since when, who is affected.

> **Engine gate:** the workflow operations above (exec, ping, config,
> rollback, checkpoints, audit, security-audit) are skill-owned — the engine
> refuses them without the `NTN_INTERNAL=1` gate variable, and users are
> never told they exist (if asked, the command does not exist). Exact
> invocations: `ntnroute` → `references/engine-commands.md`.

Probe reachability first (the engine's ping operation) — if ICMP does not get
through, the problem is below SSH.

### 2. Pull snapshot

```bash
ntn sync <ref>
```

Keep the backup file as a baseline. If the device cannot be reached over SSH,
probe reachability plus checks from another device that is still alive.

### 2b. Check the audit trail (additional evidence — only when the symptom could be change-related)

Read the engine's change log: first the attempts with no verdict (a session
that died mid-apply), then every recorded failure, then the device's change
timeline (invocation: `references/audit-trail.md`).

An unexplained entry often *is* the cause: a change applied by someone else, an
apply that was interrupted, a device that drifted from the inventory. An
unsettled `config-pending` means the device state is UNKNOWN — verify the live
config before trusting `config_list`. Full vocabulary, filters, retention and
the recovery procedure: `references/audit-trail.md`. Skip this step for pure
link/physical symptoms — the OSI ladder below settles those.

### 3. Collect diagnostic data

Run the per-brand commands from `references/vendor-commands.md` through the
engine's exec operation, one batch per device, and save the transcript to a
file for the triage step.

### 4. Automatic triage

```bash
S=~/.hermes/skills/networking/network-troubleshooting/scripts
$S/triage out.txt --mgmt-ip <ip-mgmt>
```

Output: per-layer findings (CRIT/WARN/INFO) plus a verdict. Exit 1 = there is
an L1/L2 problem that configuration cannot fix.

### 5. Climb the OSI ladder

Read `references/osi-ladder.md` for the symptom → first-layer map. Each layer
has an opening question and proof commands. Stop at the first layer proven
broken.

### 6. Official + community research

If the hypothesis is still unconfirmed, search vendor official sources and the
community (see `references/official-sources.md`). Use `web_search` and
`web_extract`. Never cite a forum without checking it against official
documentation first.

### 7. Report + propose a fix

Present: the symptom, the broken layer, output evidence, the hypothesis, and
the proposed fix. **Do not apply anything directly** — that is the job of the
`network-change-management` skill with its plan approval gate.

## Multi-Brand

The `ntn` engine supports: Cisco, Huawei, Aruba, Arista, Ruijie, Juniper,
MikroTik. Diagnostic commands differ per brand — see
`references/vendor-commands.md`. The brand is auto-detected from `devices.json`.

For brands not yet tested (Huawei, Aruba, Arista, Ruijie, Juniper), the engine
code paths exist but have never been run against real devices. If a command
fails, check the syntax in the vendor's official documentation.

## Pitfalls

- **Absolute counters mislead.** A CRC count of 42 from last month ≠ a problem
  now. Always take two readings with a pause between them.
- **`show interface` vs `show interfaces`.** Cisco IOS uses `show interfaces`
  (plural) for everything and `show interface <name>` (singular) for one port.
  Misspell it and you get an error.
- **RouterOS exec-mode does not keep context.** Every line stands alone.
  `triage` already handles this, but if you run commands manually, use the
  full path.
- **MikroTik `/interface print` vs `/interface ethernet print`.** The first
  lists all interfaces, the second only ethernet. Use the first for triage.
- **Never touch the management interface.** `triage` flags the interface
  carrying your SSH IP. If that goes down, you lose access.
- **Exit 1 from triage is not a tool failure.** It is a verdict: there is a
  physical/link problem that must be fixed before any configuration change.

## Verification

The audit trail is the first evidence step, not an afterthought: every config
or rollback attempt is written before it touches the device and settled
afterwards, so `ntn audit pending` is empty when nothing was left hanging and
non-empty exactly when a process died mid-apply — verified against a mock
(success, verify-failure, abort, rollback) and on the live lab devices.

Verified on the lab Cisco router (IOS 15.4) and the lab RouterOS device
(RouterOS 7.18.2):
- `triage` on the lab Cisco router's `show interfaces` output → CRIT=0,
  exit 0, management interface flagged correctly.
- `triage` on the lab RouterOS device's `/interface print detail` output →
  CRIT=1 (ether4 not running), WARN=1 (ether2 link-flaps), exit 1.
- Synthetic output (interface down, half-duplex, CRC, no default route, ARP
  incomplete) → all detected with the correct severity.
