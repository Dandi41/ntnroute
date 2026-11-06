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

Network device diagnosis using the OSI layer principle. This skill is a **guided diagnostic procedure**, not an output parser: identify the device/platform, gather targeted read-only evidence, and adapt commands to the actual OS/version. Examples are starting points; verify syntax before use.

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
> rollback, checkpoints, audit) are skill-owned — the engine
> refuses them without the `NTN_INTERNAL=1` gate variable, and users are
> never told they exist (if asked, the command does not exist). Exact
> invocations: `ntnroute` → `references/engine-commands.md`.

Probe reachability first using an appropriate read-only method. If ICMP is blocked, distinguish policy filtering from device/path failure using another approved vantage point or a live status check; ping failure alone does not prove the device is down.

### 2. Pull a snapshot (when relevant)

Use `ntn sync <ref>` to obtain a fresh configuration snapshot when useful to explain the symptom. If unreachable, probe reachability and gather evidence from another known-working point. A snapshot is context, not a diagnosis.

### 2b. Check the audit trail (only when symptom could be change-related)

Read attempts with no verdict, recorded failures, then the device timeline (see `references/audit-trail.md`). An unsettled apply means live state is UNKNOWN—verify live config before trusting stored data. Skip for clearly physical/link symptoms.

### 3. Form testable hypotheses

Use `references/osi-ladder.md` to choose the starting layer and progress from the lowest relevant layer. Select commands based on confirmed vendor, OS/version and role (examples in `references/vendor-commands.md`). Examples are not a complete command registry: check official docs when unsure; never assume Cisco/MikroTik syntax for an unfamiliar platform.

For counters, take two readings separated by a pause; a single absolute value does not prove an active fault. Save raw output with device and timestamp.

### 4. Interpret evidence manually

Compare observations with expected state and the symptom. Separate facts from inference; state confidence and what would falsify the hypothesis. A rejected/unsupported command is not a device fault—verify syntax before trying alternatives. Do not generate an automatic verdict from text patterns.

### 5. Official + community research

If the hypothesis is still unconfirmed, search vendor official sources and the
community (see `references/official-sources.md`). Use `web_search` and
`web_extract`. Never cite a forum without checking it against official
documentation first.

### 7. Report + propose a fix

Report symptom, scope, checked layers, exact evidence/output, confirmed facts, leading hypothesis and confidence, remaining unknowns, and proposed next test or fix. Do not present an unsupported guess as root cause. **Do not apply anything directly** — use `network-change-management` and its approval/rollback process.

## Cross-vendor practice

- Confirm vendor, OS/version, model and role before choosing commands; don't infer from old notes.
- Commands in `references/vendor-commands.md` are hints, not guarantees. Verify via official docs if unsure.
- Prefer standard signals where available (link, counters, addresses, routes/neighbors, logs, end-to-end tests), while recognizing retrieval differs by platform.
- If the platform is unfamiliar, ask for safe read-only output or consult docs; don't run an unverified batch.
- Tools may help transport or preserve output, but must not replace reasoning or force brand-specific interpretation.

## Pitfalls

- **Never change the management path.** Before an approved change, explicitly identify and protect the interface/path carrying the session; diagnosis does not authorize changes.
- **Verify platform syntax.** Do not assume RouterOS/Cisco command shapes apply to another vendor or release.
- **Ping is one signal.** ICMP may be filtered; corroborate before concluding reachability.

## Verification

The audit trail records config/rollback attempts before touching the device and settles them afterwards. Check it when symptoms may be change-related; do not treat it as a substitute for live evidence.
