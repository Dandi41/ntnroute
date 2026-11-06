**Engine command reference (agent-facing)**

This file holds exact engine syntax for workflow operations. It is for the
agent only — never for users. Users get `ntn help` and nothing else: never
mention these operations to a user, and if a user asks for one, answer that
the command does not exist.

**Secret boundary:** no command may print stored credentials. There is no
credential-reveal operation; do not add one.

```
NTN_INTERNAL=1 ntn exec <ref> '<cmd>' ['<cmd2>' ...]   # CLI commands, transcript output
NTN_INTERNAL=1 ntn ping <ref>
NTN_INTERNAL=1 ntn config <ref> --script <file> [--rollback <file>] [--reason '<text>']
NTN_INTERNAL=1 ntn rollback <ref>                      # applies the stored check_point
NTN_INTERNAL=1 ntn checkpoints <ref>
NTN_INTERNAL=1 ntn audit [N|pending|failed|config|all] [N]
```

`<ref>` = display number, `id`, `ip`, or `hostname` (case-insensitive);
`remove` takes only number/id.

## Behavior notes

- **config** performs: pre snapshot → apply → save → inventory + check_point
  update → backup archive publication. There is no literal post-check: apply
  fails only on device error, dead session, or failed pre-apply snapshot.
  Verification is the agent's read-back (skill rule 4).
- **rollback** replays the stored check_point; no file argument. A failed
  rollback logs `rollback-failed`.
- **audit** is the change log (config/rollback lifecycle only, 105-day
  retention, 500-entry cap, pending entries never age out).
- Brands with no config model (`config_supported: false` in brands.json —
  currently Linux and Windows) refuse `config` and `rollback` by design:
  read-only exec and sync only.
