**Engine command reference (agent-facing)**

This file holds exact engine syntax for operations that are not exposed in the
public menu. It is for the agent, not for users: users get `ntn help` only.

**Secret boundary:** no command may print stored credentials. There is no
credential-reveal operation; do not add one.

```
NTN_INTERNAL=1 ntn exec <ref> '<cmd>' ['<cmd2>' ...]   # CLI commands, transcript output
NTN_INTERNAL=1 ntn ping <ref>
NTN_INTERNAL=1 ntn config <ref> --script <file> [--rollback <file>] [--reason '<text>']
NTN_INTERNAL=1 ntn rollback <ref>                      # applies the stored check_point
NTN_INTERNAL=1 ntn checkpoints <ref>
NTN_INTERNAL=1 ntn audit [N|pending|failed|config|all] [N]
NTN_INTERNAL=1 ntn security-audit <ref|all> [--trigger explicit|quarterly]
NTN_INTERNAL=1 ntn security-audit-list [N]
NTN_INTERNAL=1 ntn security-audit-show <run-id>
```

`<ref>` = display number, `id`, `ip`, or `hostname` (case-insensitive);
`remove` takes only number/id.

## Behavior notes

- **config** performs: pre snapshot → apply → save → post-check (every script
  line must appear in the new config) → inventory + check_point update →
  backup archive publication. Exit 0 only on full success.
- **rollback** replays the stored check_point; no file argument. A failed
  rollback logs `rollback-failed`.
- **audit** is the change log (config/rollback lifecycle only, 105-day
  retention, 500-entry cap, pending entries never age out).
- **security-audit** runs the read-only hardening battery on every matched
  device and records the run under `.security_audits` (last 100 kept).
- Brands with no config model (`config_supported: false` in brands.json —
  currently Linux and Windows) refuse `config` and `rollback` by design:
  read-only exec and sync only.
