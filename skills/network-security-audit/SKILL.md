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

Read-only during the audit; remediation goes through the `network-change-management` skill. The audit is a **guided procedure**, not a vendor-specific parser: identify platform from live evidence, choose safe read-only commands, interpret output, and research uncertain findings. Never assume examples are supported on every release.

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
- After an incident: audit + `network-troubleshooting` for forensics

Not for: changing config (→ `network-change-management`), diagnosing
outages (→ `network-troubleshooting`), adding devices (→ `ntnroute`).

## Audit Procedure

### 1. Confirm scope with the user

One short question: audit one device or all of them? Focus on local,
perimeter, or both? Don't assume.

### 2. Collect live evidence (manual, read-only)

Use the `ntnroute` skill's approved read-only access. Do not use a pre-baked audit script: syntax and output vary across vendors, OS versions, roles, and models.

1. Identify vendor/OS/version and device role from inventory and live evidence; if uncertain, ask for safe version/show output.
2. Choose relevant checks from `references/baselines.md` and official docs. Ask for missing context (e.g. intended management source ranges or exposed services).
3. Run a small batch of relevant read-only commands and retain raw output. If syntax is rejected, verify it from official docs before alternatives.
4. If unreachable, report **unknown / not audited**, never secure.
5. Verify feature applicability; separate observed facts from inference and state confidence.

For multiple devices, repeat and record findings per device. Never claim the fleet is clean if devices/checks were unreachable or unverified.

### 2b. Check the change log (when change-related)

Read the config/rollback timeline and attempts with no verdict (`network-troubleshooting` → `references/audit-trail.md`). Record out-of-band changes and unsettled applies; verify live config before trusting stored snapshots.

### 3. CVE + version research (if requested or a suspicious version shows up)

Identify exact product, OS train, version, hardware/model and relevant features. Follow `references/threat-research.md`: vendor PSIRT first → verify in NVD → confirm affected/fixed versions and feature relevance. Cite URLs; state when unverified.

### 4. Assess against the baseline

Use `references/baselines.md` as a framework, not a vendor parser or exhaustive oracle. Adapt to platform and role; distinguish `not applicable`, `not checked`, and `unknown`. Verify command examples against official docs.

### 5. Assemble the report

Use `templates/audit-report-template.md`: scope, inventory, reachability/completeness, evidence-backed findings with confidence, sources/CVEs, perimeter exposure, limitations, and proposed hardening. Do not execute remediation or recommend recurring audits.

## Division of labor across networking skills

| Skill | Role |
|---|---|
| `ntnroute` | inventory, transport, `ntn config`/rollback |
| `network-device-cli` | how to SSH to devices directly (outside ntn) |
| `network-troubleshooting` | outage diagnosis, OSI layers, hypothesis tests |
| `network-change-management` | change approval, rollback generation |
| `network-security-audit` (this) | security findings, CVE/baseline, audit report |

Complementary flow: the audit (this skill) finds → the user approves
remediation → `network-change-management` plans it, gets approval, and
applies it → `network-troubleshooting` verifies nothing broke.

## Pitfalls

- **CVE findings require applicability evidence.** Match product/model/build, affected versions, and enabled features before assigning severity.
- **Version ≠ patch level.** Verify release notes and fixed-version advisories; do not infer patch status from version numbering alone.
- **The perimeter needs an outside vantage point.** Configuration shows intended policy, not measured reachability. Active external tests require explicit permission and documented scope.
- **Unknown is not safe.** Mark unreachable or unverified checks unknown/not checked, not pass.
- **Don't run an audit unrequested.** This is a user rule, not a preference.
- **Audit ≠ outage diagnosis.** Use `network-troubleshooting` for availability/performance symptoms.

## Verification

This is a guided, read-only workflow with no bundled parsers. Gather actual output, adapt to the device, and cite sources for externally verified claims. Audit runs are not recorded in the device inventory: the audit report is the record.
