# Engine release checks — verify on the live lab after engine changes

Run in this order: no-device checks first, read-only device paths next,
config+rollback last and only through the change gate. Establish reachability
before anything else — the lab VMs are powered off more often than on, and
"exec failed" on a powered-off lab is not a regression.

## 1. No-device checks

- `bash -n ntn` — syntax gate.
- Unit-test each changed function in isolation: extract with
  `sed -n '/^name()/,/^}/p'` and `eval`, then exercise it.
  - Case helpers (`lc`/`ucfirst`/`norm_brand`/`norm_type`): mixed-case and
    unknown inputs; compare against the pre-change behavior.
  - `month_for`: engine stamp `YYYYMMDD-HHMMSS`, ISO date, garbage (must fall
    back without error).
- Retention on a synthetic tree: create more than 4 change pairs and more than
  4 sync snapshots in one month dir, run `retain_backups <host>`, expect
  exactly 4 of each kept.
- `archive_pair` with migration in the loop: publish a pair, then assert the
  staging rollback copy is gone and nothing loose remains under `$BACKUP_DIR`.
  The cleanup must live inside `archive_pair` before `retain_backups` runs —
  migration relocates the staging file, so a cleanup placed after the call
  misses it.

## 2. Read-only device paths (no gate)

- `ntn list` + `ntn show <ref>` — exercises the brand-normalization path on
  real inventory.
- Multi-line exec batch per session mode: RouterOS exec-mode (several `/...`
  commands) and Cisco PTY (enable → paging → several `show`). Include a piped
  IOS command (`show running-config | section ospf`).
- `ntn sync <ref>` then `ntn sync all` — exercises config pull, `month_for`,
  archive publication, `retain_backups`, `migrate_backups`.
- After sync: no orphan rollback file anywhere under `backups/`. Published
  pairs match `*-<digits>.rollback.cmd`; a bare `<stamp>-rollback.cmd` is an
  orphan duplicate that eats a sync-snapshot retention slot. Remove one only
  after `diff` proves it identical to its pair.
- One rejected command fails the whole exec batch (exit 1) — split the batch
  command-by-command to isolate the offender before blaming the engine. Known
  non-fault: `/system routerboard print` on CHR (QEMU x86 has no routerboard).

## 3. Config + rollback full cycle (gate required — 5-block plan first)

One cycle per session mode, on a throwaway object:

- RouterOS: add an address with a unique comment on an unused interface; the
  rollback removes by that exact comment (never a bare `[find]`).
- Cisco: create a new Loopback block; `rollback_gen` emits
  `no interface LoopbackNN` for a block that did not exist before — no TODO
  filling needed for that shape.
- Each cycle: apply → read-only verification (expected output written before
  apply) → `ntn rollback <ref>` → verification of clean state →
  `check_point` cleared.
- After both cycles: the audit trail shows `config-pending → config-started →
  config-ok` and `rollback-started → rollback`; no staging duplicates anywhere
  under `backups/`.
