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
3. **Evidence, not opinion.** Every finding has command output plus, for
   CVEs, an official link. Without a link → write "not yet verified".
4. **Both sides:** local (device hardening) and perimeter (what can be
   reached from outside). The perimeter is usually the more fatal side.
5. **CVEs from research, not memory.** The OS version comes from the device,
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

```bash
S=~/.hermes/skills/networking/network-security-audit/scripts
python3 $S/sec_audit.py <ref> [--cve] [--config <backup.cfg>]
```

The script runs a read-only command battery per brand via `ntn exec`
(services, users, SSH, firewall, OS version), parses the transcripts, and
reports findings per category. Exit 1 = a CRIT exists. `--config` adds the
config rules from `cfg_audit.py`.

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
| `network-troubleshooting` | outage diagnosis, OSI layers, `triage.py` |
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
