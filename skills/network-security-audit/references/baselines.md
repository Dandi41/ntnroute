# Hardening baseline: general assessment prompts

Use this as a framework, not a brand-agnostic parser or pass/fail oracle. Confirm applicability for exact model, OS/version, deployment role, and intended policy. Gather live read-only evidence. Mark each item `verified`, `not applicable`, `not checked`, or `unknown`.

## Management plane
- Are administrative services limited to intended protocols and source ranges?
- Is authentication strong and least-privilege? Is plaintext management avoided?
- Are unused accounts/services disabled and session timeouts reasonable?
- Is management isolated from untrusted user/data planes?

## Perimeter and forwarding
- What can reach the device and transit through it from each trust zone?
- Are policies explicit, correctly ordered, least-privilege, and observable through counters/logs?
- Do NAT/port-forward rules expose management or unintended services?
- Are anti-spoofing and default-deny expectations appropriate for this role?

## Platform and operations
- Is the exact OS/model supported and receiving security updates?
- Are logs, time sync, backups, and administrative access protected?
- Are protocols, routing adjacencies, and control-plane services limited to intended peers?

Verify commands and recommendations with official vendor docs for the exact platform. No checklist is exhaustive.

## Severity scale used

- **CRIT** — verified high-impact exposure or control failure, supported by evidence and applicable to device context.
- **WARN** — substantiated weakness that increases risk under stated conditions.
- **INFO** — contextual note or improvement, not necessarily a vulnerability.