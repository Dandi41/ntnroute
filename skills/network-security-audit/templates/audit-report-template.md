# Security audit report template

Fill in every section. Every finding carries verbatim evidence and, for CVEs, an
official link. Control IDs come from `references/baselines.md`; phase numbers
from `references/audit-playbook.md`.

Send the finished report to the user. Remediation only after they approve it,
and only through `network-change-management`.

---

## Security Audit Report — <hostname> (<ip>)

**Audit date:** <YYYY-MM-DD>
**Scope:** <one device / list / fleet> — local / perimeter / both
**Role:** <edge router / core switch / access switch / CPE / lab box — this
decides severity>
**Vendor / model:** <vendor> <model>
**OS:** <product> <version> <train/channel> <build>
**Support status:** <supported / EOL / unknown — with link>
**Reference baseline:** `references/baselines.md` v<ver>, plus <any vendor
hardening guide used, with link>
**CVE research date:** <YYYY-MM-DD> (CVE lists go stale)
**Checks completed:** MGT-01…09, PER-01…10, CTL-01…08, OPS-01…06 — list the IDs
actually verified
**Not checked / unknown:** <control IDs plus the reason: unreachable,
inaccessible, unsupported on this platform, output unusable>
**Limitations:** <vantage point, assumptions, active tests not performed,
features that could not be confirmed as in use>

### Summary

| Sev | Count | Summary |
|---|---|---|
| CRIT | n | <one sentence> |
| WARN | n | <one sentence> |
| INFO | n | <one sentence> |

**Verdict:** FAIL (CRIT present) / PASS with notes / NOT ASSESSED (device
unreachable).
Never write "secure". Write "no findings against this baseline as of <date>,
with these checks not performed: …".

### Findings — local network

One block per finding:

```
[CRIT] MGT-01 — telnet server enabled and listening on all interfaces
Phase:       2 (management plane)
Evidence:    /ip service print
               telnet  23  any    yes
Impact:      Cleartext administrative credential capture from any reachable
             segment; combined with MGT-02 the exposure reaches the WAN side.
Remediation: /ip service disable telnet   (proposal — goes through the change
             workflow with rollback, not applied by this audit)
Confidence:  verified from live output
```

Severity rules: a **combination** finding outranks either half. Telnet enabled
is MGT-01; telnet enabled *and* reachable from the WAN is MGT-01 + MGT-02 +
PER-03, and that is what actually gets exploited. Say which controls the finding
covers.

### Findings — perimeter (outside-in)

What is reachable from each trust zone, in rule order:

```
Outside interface: <name> (<ip>/<prefix>)
Default action:    <drop / accept>
Exposed services:  <service → protocol/port → first matching rule → verdict>
NAT exposure:      <rule → what it forwards → does it reach a management port>
Anti-spoofing:     PER-05 <present / absent — BCP 38>
Measured:          <intended policy only — NOT measured>  OR
                   <active test: tool, time, source network, permission, results>
```

If you did not test from outside, say `intended policy only — not measured`.
Configuration proves intent, not reachability.

### Findings — version & CVE

```
<os> <version> <build> | lifecycle: <supported/EOL, link>
CVE-<id> | CVSS <x> | <component/feature> | affected range matches: <yes/no> |
device uses feature: <yes/no — evidence> | <official link> | verdict: <CRIT/WARN/INFO + why>
```

A CVE whose affected feature is not in use is recorded as INFO **with the
reason**, never dropped and never inflated. No link → write `not yet verified`.

### Findings — change trail

```
Unsettled applies: <count + timestamps>  → live state UNKNOWN, verify before trusting
Out-of-band changes: <diff summary + timestamp>
Trail matches live config: <yes/no>
```

### Hardening plan (proposed, not executed)

Priority order, CRIT first. Per step:

```
1. <control ID> — <action>
   Command:  <exact command>
   Rollback: <exact reverse command>
   Risk:     <what breaks if this is wrong; does it touch the management path>
```

Application is `network-change-management`: plan gate, approval, rollback,
verification. This audit does not execute it and does not decide whether the
user may make the change.

### Not covered

Everything that could not be audited this time, named explicitly: platform
without a confirmed command path, no outside vantage point, no active-test
permission, features whose use could not be established, checks where the
device was mid-maintenance. This section is what makes the report honest
rather than decorative.