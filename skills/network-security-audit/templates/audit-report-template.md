# Security audit report template

Fill in every section. Every finding has evidence (command output) and, for
CVEs, an official link. Send it to the user — remediation only after approval.

---

## Security Audit Report — <hostname> (<ip>)

**Audit date:** <YYYY-MM-DD>
**Scope:** local / perimeter / both
**Vendor/OS:** <brand> <os + version + channel> — support status: <active/EOL, link>
**Reference baseline:** <name/version of any reference used>
**CVE research sources:** <URLs cited, with access dates>
**Checks completed:** <controls actually verified>
**Not checked / unknown:** <unreachable, inaccessible, unsupported, or insufficient evidence>
**Limitations:** <scope, vantage point, assumptions, versions>

### Summary

| Sev | Count | Summary |
|---|---|---|
| CRIT | n | <one sentence> |
| WARN | n | <one sentence> |
| INFO | n | <one sentence> |

**Verdict:** FAIL (CRIT present) / PASS with notes.

### Findings — local network

Per-finding format:

```
[CRIT] <rule-id> — <one-sentence cause>
Evidence:    <verbatim command output lines>
Impact:      <what could happen>
Remediation: <exact command/action> (goes into the hardening plan, needs approval)
```

### Findings — perimeter (outside-in)

What can be reached from outside: service list + filter state + NAT.
If active testing was done (port scan from outside): name the tool, the
time, the results, and the user's permission.

### Findings — version & CVE

```
<os+version> | status: <supported/EOL, link>
CVE-<id> | CVSS <x> | component <feature> | device uses the feature? <yes/no> | link
```

Irrelevant CVEs are still recorded (INFO) with the reason they are irrelevant.

### Hardening plan (proposed, not yet executed)

Priority order: CRIT first. For each step: exact command + rollback +
risk. Execution goes through the `network-change-management` skill (plan
approval + rollback) once you approve.

### Not covered

State what couldn't be audited this time (untested brand, no access from
outside, no port-scan permission) so the report stays honest.
