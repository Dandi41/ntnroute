---
name: network-security-audit
description: "Audit network device security: local hardening and perimeter."
version: 1.0.0
author: Dandi Suryadi, Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [network, security, audit, cve, hardening, perimeter, cisco, mikrotik, compliance]
    related_skills: [ntnroute, network-device-cli, network-change-management, network-troubleshooting]
---

# Network Security Audit

Security audit of network devices: device hardening (local network) and
exposure to the outside (perimeter). Read-only during the audit; remediation
goes through the `network-change-management` skill.

## Core rules

1. **Audit only when the user asks.** Never run an audit proactively
   ("while we're at it", "to be thorough"). Triggers: the user requests an
   audit, a security check, or an incident that needs a security assessment.
2. **Read-only.** All audit commands are read-only (`show`, `print`,
   `display`). No state changes during the audit.
3. **Report, never authorize or veto.** A security audit produces evidence,
   severity, and remediation advice only. It never blocks, permits, delays,
   or otherwise decides a requested configuration change — including a change
   that removes DHCP clients, firewall rules, services, routes, or accounts.
   The user decides whether to change configuration; the change workflow
   handles consent, rollback, and verification separately.
4. **Evidence, not opinion.** Every finding has command output plus, for
   CVEs, an official link. Without a link → write "not yet verified".
5. **Both sides:** local (device hardening) and perimeter (what can be
   reached from outside). The perimeter is usually the more fatal side.
6. **CVEs from research, not memory.** The OS version comes from the device,
   CVEs are researched via the web from official sources (vendor PSIRT →
   NVD), and relevance is checked against the features actually in use.

## When to Use

- User asks: "audit the security of the lab RouterOS device", "check network
  security", "is this device secure?"
- Before a new device goes into production (initial audit)
- Periodically (e.g. monthly) — but still user-requested, not automatic
- After an incident: audit + `network-troubleshooting` for forensics

Not for: changing config (→ `network-change-management`), diagnosing
outages (→ `network-troubleshooting`), adding devices (→ `ntnroute`).

## Audit Procedure

### 1. Confirm scope with the user

One short question: audit one device or all of them? Focus on local,
perimeter, or both? Don't assume.

### 2. Collect live data

For ONE device:

```bash
S=~/.hermes/skills/networking/network-security-audit/scripts
python3 $S/sec_audit.py <ref> [--cve] [--config <backup.cfg>]
```

The script runs a read-only command battery per brand via `ntn exec`
(services, users, SSH, firewall, OS version), parses the transcripts, and
reports findings per category. Exit 1 = a CRIT exists. `--config` adds the
config rules from `cfg_audit.py`.

For MULTIPLE devices (an audit usually touches more than one), use the
engine's multi-device audit operation — it runs the same battery on every
matched device and records the run. These workflow operations are
skill-owned: they require the `NTN_INTERNAL=1` gate variable (the engine
refuses them without it; `sec_audit.py` sets it itself when it spawns
`ntn exec`). Invocation: `ntnroute` → `references/engine-commands.md`.

The workflow: run the audit (per-device WARNING/UNREACHABLE lines come back),
list recent runs, and show the full per-device findings of the latest run.
The run is persisted in `devices.json` under `.security_audits` (last 100
kept) with per-device status, OS version, findings, and severity counts —
so a multi-device audit is recorded once, with every device's result and
notes, even the unreachable ones. Exit 1 = at least one device has a
CRITICAL; exit 2 = at least one device was unreachable. Report BOTH kinds
of warning to the user; an unreachable device must not be treated as safe.

### 2b. Check the change log (additional evidence)

Read the engine's change log for the device's config/rollback timeline and
for attempts with no verdict — an apply that died mid-flight
(invocation: `network-troubleshooting` → `references/audit-trail.md`).

Changes made outside the approval gate, or an apply that never reported a
verdict (device state may not match the inventory's `config_list`), are findings
in their own right — record them with their timestamp. Vocabulary and recovery
steps: `network-troubleshooting` → `references/audit-trail.md`.

### 3. CVE + version research (if requested or a suspicious version shows up)

`--cve` prints the detected OS version plus the research procedure. Run the
research yourself via `web_search` following `references/threat-research.md`:
version EOL status → CVEs per version on the vendor PSIRT → verify on NVD →
check feature relevance → record with links.

### 4. Assess against the baseline

Compare findings with `references/baselines.md` (Cisco, MikroTik; other
brands use the generic config audit + vendor baselines). Mark which items
are covered by the checklist and which are not.

### 5. Assemble the report

Format in `templates/audit-report-template.md`: scope, inventory, findings
(CRIT/WARN/INFO + evidence + CVE + remediation), perimeter exposure,
hardening plan. Send it to the user — don't execute remediation directly.

Close the report with the routine-audit recommendation: a security audit
like this should repeat every 3 months (quarterly cadence).

### 6. Remediation (only after the user approves)

Hardening plan → write the script → `cfg_audit.py --change` gate → plan
approval gate (5 blocks) → `ntn config` with rollback. All of that is the
`network-change-management` skill's job; this skill stops at report +
proposal.

## Division of labor across networking skills

| Skill | Role |
|---|---|
| `ntnroute` | inventory, transport, `ntn config`/rollback |
| `network-device-cli` | how to SSH to devices directly (outside ntn) |
| `network-troubleshooting` | outage diagnosis, OSI layers, `triage` |
| `network-change-management` | change gate, approval, rollback, `cfg_audit.py` |
| `network-security-audit` (this) | security findings, CVE/baseline, audit report |

Complementary flow: the audit (this skill) finds → the user approves
remediation → `network-change-management` gates and applies it →
`network-troubleshooting` verifies nothing broke.

## Pitfalls

- **CVE without a feature check.** A CVE for an unused feature is INFO, not
  CRIT. Check whether the device config actually uses that feature.
- **Version ≠ patch level.** RouterOS 7.18.2 stable may or may not already
  include the patches — check the release changelog on supportsec, not just
  the version number.
- **The perimeter needs an outside vantage point.** `sec_audit.py` reads
  filter config; for real evidence, test from an outside network (port scan
  from outside) — ask the user for permission first, and note in the report
  that it was active testing.
- **Untested brands.** Huawei/Aruba/Arista/Juniper/Ruijie have no live
  battery in `sec_audit.py` — use the generic config audit + vendor
  baselines, don't invent commands.
- **Don't run an audit unrequested.** This is a user rule, not a preference.
- **Counters/errors in an audit ≠ diagnosis.** If the user reports an
  outage, that's `network-troubleshooting`; a security audit doesn't answer
  "why is it slow".

## Verification

Config/rollback history is part of the evidence base: `ntn audit config 50`
gives the device timeline (pending → started → ok/failed/aborted) and
`ntn audit pending` lists only attempts with no verdict at all. The engine
writes the `-pending` entry *before* touching the device, so the trail covers
interrupted applies too — verified against a mock (success, verify-failure,
abort, rollback) and on the live lab devices.

Proven on the lab RouterOS device (RouterOS 7.18.2) and the lab Cisco router
(IOS 15.4(2)T4):
- Lab RouterOS device: CRIT=5 — telnet/ftp/www/api enabled + empty input
  chain (perimeter); WARN=4 — strong-crypto no, admin user expired, empty
  inactivity policy; exit 1. Detected version: RouterOS 7.18.2.
- Lab Cisco router: CRIT=0, WARN=1 — DEVELOPMENT TEST image build (not a
  production build); INFO=3 — HTTP server disabled (good), version recorded
  for CVE. Exit 0.
- Live CVE research: `mikrotik.com/supportsec` (official advisories), CERT
  Polska, NVD — the web_search → official source flow is proven to work.
