---
name: network-change-management
description: "Gate network changes: plan, approval, rollback, verify."
version: 1.1.0
author: Dandi Suryadi, Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [network, cisco, mikrotik, routeros, audit, rollback, change-management]
    related_skills: [ntnroute, network-device-cli, network-troubleshooting, network-security-audit]
---

# Network Change Management

Two stdlib-Python gates that sit between "change script drafted" and "apply to device". They never touch hardware — they decide whether a change is safe to run, and they produce the undo for it. Pairs with the `ntnroute` skill: gate first, then `ntn config`.

- `scripts/cfg_audit.py` — audits a saved running-config (CRIT/WARN/INFO hardening findings) and, with `--change`, gates a pending change script for lockout risk before it goes anywhere near a device.
- `scripts/rollback_gen.py` — derives a rollback script from the change script, applying the rules a naive `no <line>` prefixer gets wrong (blocks, negations, creates vs edits).

Both print text verdicts and exit 1 when a CRITICAL finding applies to the decision at hand.

## When to Use

- Before any `ntn config <ref> --script ...` run: gate the script first.
- After `ntn sync`, or on any file in `~/.ntnroute/backups/`: audit the saved config for hardening findings.
- When a change script exists but the rollback script does not.

Don't use for executing changes (`ntn config`), reading live state (`ntn exec`), or plain Linux boxes over SSH.

## Plan approval gate — HARDLINE

No `ntn config` (and no `ntn exec` carrying a write command) until the user has
seen all five blocks below in chat and replied with an explicit go-ahead. This
holds even when the user asked for the change in the same message, and even when
the change is "just one line".

1. **Plan + brief rationale** — what changes, why, what it fixes or enables.
2. **Configuration to be applied** — the exact script, verbatim, in a code
   block. Not a summary, not "and similar lines".
3. **Rollback** — the exact undo script, verbatim (from `rollback_gen.py`).
4. **Post-apply verification** — the exact read-only command that proves it
   worked, and the expected output token or state. Written before applying, never
   invented after.
5. **Risk** — BLOCKED / WARN / CLEAN from the gate, plus which lines the gate
   flagged and why they are acceptable.

Then stop. End the turn and wait. Fill `templates/plan-template.md` — it is the
same five blocks in the shape the user reads.

- Approval covers **exactly** that script. If any line changes after approval —
  even one character, even after the gate passed — re-gate and re-ask. The old
  yes is void.
- "Continue", "ok", "go ahead" on a *different* message counts as approval for the plan
  shown immediately before it. A generic "do it" that arrives **before** any
  plan has been shown is not approval — show the plan first.
- Never apply a subset to "test the waters" and never chain a second unreviewed
  change after a successful one.
- If verification after apply does not show the expected state, report the real
  output and stop. Do not re-apply, do not fix it with an unplanned change.

## Procedure — before every config change

1. Fresh baseline: `ntn sync <ref>` via `terminal`. The gate is only as good as
   the config file it reads. Note the new file under `~/.ntnroute/backups/`.
2. Write the change script to the scratch dir.
3. Gate the change:

```bash
S=~/.hermes/skills/networking/network-change-management/scripts
python3 $S/cfg_audit.py --change change.cmd --config <synced>.cfg \
  --mgmt-ip <ip> [--mgmt-interface <iface>]
```

4. Act on the verdict: `PROCEED` (exit 0) → continue; `REWRITE` (exit 1) → fix
   every CRIT line the gate names, then re-gate. Never apply a REWRITE change.
5. Generate the rollback:

```bash
python3 $S/rollback_gen.py change.cmd --existing-config <synced>.cfg --out rollback.cmd
```

6. Read `rollback.cmd` line by line, fill every `# TODO restore from snapshot:`
   from the pre-change config, narrow Mikrotik `remove [find]` placeholders.
7. Present the five blocks from **Plan approval gate** and end the turn.
8. Only after the explicit go-ahead: `ntn config <ref> --script change.cmd
   --rollback rollback.cmd --reason '<the plan reason>'`.
9. Verify with the command promised in block 4 via `ntn exec`, quote the device's
   own output line, and compare against the expected token. `ntn config`'s
   post-check passing is not verification — read the state back.
10. Report: changed lines confirmed, verification output, config_list/check_point
    updated. If anything is missing, say so plainly and stop.

Config-only audit (no pending change): `python3 $S/cfg_audit.py <file.cfg> --mgmt-ip <ip>` — CRIT findings end with `VERDICT: HARDENING REQUIRED` and exit 1. Those are separate work items, not blockers for unrelated changes.

## Pitfalls

- **DHCP management IP.** When the mgmt address is DHCP the audit cannot resolve which interface carries the SSH session, and mgmt-interface findings drop to WARN. Pass `--mgmt-interface <name>` so a lockout line stays CRIT.
- **Report the plan in plain language first.** One-line analogy for
  the mechanism, then the blocks. The user's approval is on the *content*, so the
  plan must be readable without decoding CLI jargon.
- **A successful apply is not the end.** Block 4's verification command is a
  promise; skipping it because `ntn config` printed `STATUS: SUKSES` is the
  failure mode this gate exists to stop.
- **Gate and audit verdicts are separate.** With `--change`, pre-existing config findings print as context but change neither the verdict nor the exit code — a pre-existing plaintext password must not block an unrelated interface edit. Harden it separately.
- **Mikrotik rollbacks are placeholders.** RouterOS has no `no` form; `rollback_gen.py` emits `remove [find]  # TODO: narrow the find`. Narrow it to the exact object before use.
- **`no shutdown` rollbacks re-shut the link.** Emitted with a `# WARNING` comment — that is the blast-radius case; decide consciously, don't paste blindly.
- **TODO lines are deliberately incomplete commands.** The pre-change value exists only in the pre-change snapshot, never in the change script; the tool refuses to guess.
- Vendor auto-detects from config text (RouterOS `/export` vs Cisco-style); pass `--vendor` only for ambiguous files.

## Verification (proven against snapshots from the lab Cisco router and the lab RouterOS device)

- Benign change (description + `no shutdown` on a non-mgmt port) → PROCEED, exit 0. Change touching the mgmt interface → REWRITE, exit 1. With `--mgmt-interface` supplied, the DHCP-mgmt lockout line is CRIT again.
- New `vlan 40` / `interface Loopback99` blocks roll back to `no vlan 40` / `no interface Loopback99`. `no interface Ethernet0/2` against a pre-existing interface → UNSAFE, exit 1.
- `no ip http server` recognized as idempotent (omitted, explained); `no ip address ...` as destructive (TODO + snapshot note).
