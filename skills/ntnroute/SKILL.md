---
name: ntnroute
description: Manage NTnRoute network devices via `ntn` CLI.
version: 1.1.0
author: Dandi Suryadi
license: MIT
metadata:
  hermes:
    tags: [network, ssh, cisco, huawei, mikrotik, routeros, inventory, config-management]
    related_skills: [network-device-cli, network-change-management, network-troubleshooting, network-security-audit]
---

# NTnRoute.AI — network device engine

## When to Use

Use when the user asks about network devices in the NTnRoute inventory: listing/adding/removing devices, running CLI commands on them, pulling config, applying config changes, rollback, or troubleshooting connectivity.

Use when managing, configuring, or troubleshooting network devices in the NTnRoute inventory (Cisco, Huawei, Aruba, Ruijie, Arista, Juniper, Mikrotik, Fortinet).

Port of the n8n NTnRoute.AI workflow to Hermes. Persistence lives in a plain JSON file, not in a conversation: device data survives session changes, `/new`, and restarts.

Storage: `~/.ntnroute/devices.json` (mode 600). Backups: `~/.ntnroute/backups/`. Engine: `ntn` on `$PATH` (`~/.ntnroute/ntn`).

## Mandatory principles

1. **Anti-hallucination.** Never invent IP/interface/VLAN/credential values. Check `ntn list` + `ntn show <ref>` first. Still missing → ask the user specifically before assembling a script. The inventory changes between sessions (devices are added/removed/replaced), so `ntn list` is the single source of truth — do not use old session notes, memory, or the test table in this skill as the list of active devices. The test table below is test history only, not an inventory.
2. **Read-only first.** `ntn exec <ref> 'show ...'` before proposing any change.
3. **Approval required — plan first.** Before `ntn config`, show the user: (a) the plan + short reason, (b) the exact config script, (c) the exact rollback script, (d) the post-apply verification command + expected output, (e) the verdict gate. Then stop and wait for an explicit answer. Running `ntn config` without explicit approval is a violation — including when the user asks for the change in the same message or the change is "just one line". If even one line of the script changes after approval, the old approval is void — re-gate and ask again. Details: the `network-change-management` skill, section "Plan approval gate".
4. **Verify after apply.** `STATUS: SUCCESS` from the engine is not final proof — run the verification command promised in the plan via `ntn exec`, quote the device output lines, and compare against what was expected. Mismatch → report as-is; do not re-apply or patch with unplanned changes.
5. **Blast radius.** Never touch the management path/VTY/SSH access-class/default route that the AI itself depends on. Lockout = total failure.
6. **Surgical.** Only the targeted interface/VLAN/process. No speculative commands. Follow the existing naming conventions.
7. **Paging.** The engine already inserts `terminal length 0` / `screen-length 0 temporary` / `no page` / `set cli screen-length 0` automatically. Do not add them yourself.
8. **Checkpoint mandatory.** The `check_point` column + pre/post snapshots in `backups/` are created automatically by the engine. Rollback = `ntn rollback`.
9. **Save config.** `write memory` / `save`+`Y` / `commit` are appended automatically at the end of a config script.
10. **Post-check loop.** The engine already verifies that every line of the script appears in the new running-config. On `STATUS: FAILED`, analyze the device error output, fix the script, retry; total failure → `ntn rollback`.
11. **Honesty.** Report real results from tool output, including failures. No speculation.

## Commands

**Menu rule (first contact).** When the user types `ntn` alone, asks "what can ntn do", or wants the command list: run `ntn help`, then present EVERY command from the block below — all 11, each with its arguments and a clear one-line explanation of what it is for, written in the user's language. Never compress the menu into grouped bullets (e.g. "ping / exec / sync — tes & baca"), never drop commands, never replace the menu with a summary. The full menu IS the answer; a short closing question ("mau mulai dari mana?") is fine.

```
ntn list                                   # numbered list (id, hostname, ip:port, brand, last_sync)
ntn add <IP> <Port> <User> <Pass> <Type> <Brand> [Secret]
ntn show <ref> [--reveal]                  # details + config_list; --reveal shows password/secret
ntn remove <number|id>                     # after showing the list
ntn ping <ref>
ntn exec <ref> '<cmd>' ['<cmd2>' ...]      # CLI commands, transcript output
ntn sync <ref|all>                         # pull running-config -> config_list + backup
ntn config <ref> --script <file> [--rollback <file>] [--reason '<text>']
ntn rollback <ref>
ntn checkpoints <ref>
ntn audit [N]
```

`<ref>` = display number, `id`, `ip`, or `hostname` (case-insensitive).

## Workflows

### Add a device
When the user asks to add a device, require the standard format and reject anything else:
```
/add <IP> <Port> <Username> <Password> <Type> <Brand> [Secret]
```
Normalize Type/Brand capitalization yourself (router→Router, cisco→Cisco, olt→OLT). Then `ntn add ...`. Hostname and config_list are filled automatically from the device (the engine tests SSH first; failure = nothing is saved).

Secret is only for brands that need level-2 verification (Cisco `enable secret`, Huawei `super`).

### Remove a device
Do not delete immediately. `ntn list` → ask the user for the row number → `ntn remove <number>`.

### Troubleshooting
1. `ntn list` / `ntn show <ref>` for context.
2. `ntn exec <ref> 'show ip interface brief' 'show ip route' ...` — read the real condition.
3. Web research on syntax/best practices for the brand is allowed.
4. Propose the fix + script, show the 5-block plan (plan+reason, config, rollback, verification, verdict gate), request approval.
5. After success, clean up artifacts (scratch files in `$TMPDIR`, no logs left on the device).

### Config change (full workflow)
```bash
# 1. the change script
cat > "$TMPDIR/change.cmd" <<'EOF'
interface Ethernet0/2
 description uplink-BACKBONE
 no shutdown
EOF
# 2. fresh baseline + blast-radius gate — MANDATORY (network-change-management skill)
ntn sync <ref>   # audit prefers a config that was actually read; note the new file in ~/.ntnroute/backups/
S=~/.hermes/skills/networking/network-change-management/scripts
python3 $S/cfg_audit.py --change "$TMPDIR/change.cmd" \
  --config ~/.ntnroute/backups/<file-from-sync>.cfg --mgmt-ip <mgmt-ip>
# If the mgmt IP is DHCP-learned: add --mgmt-interface <iface> so lockout stays CRIT.
# VERDICT REWRITE (exit 1) = fix the script, re-gate. PROCEED = continue.
# 3. generate rollback, read it line by line, fill in "# TODO restore from snapshot:" from the pre-config
$S/rollback_gen "$TMPDIR/change.cmd" \
  --existing-config ~/.ntnroute/backups/<file-from-sync>.cfg \
  --out "$TMPDIR/rollback.cmd"
# MikroTik: the result contains `remove [find]` placeholders — narrow each find to the
# object the change actually added.
# 4. show the change + rollback to the user, ask permission, then:
ntn config 1 --script "$TMPDIR/change.cmd" \
  --rollback "$TMPDIR/rollback.cmd" --reason 'short reason'
```
The engine performs: pre snapshot → apply → save → post-check → update `config_list` + `check_point`. Success only when there are no device errors AND every script line appears in the new config.

`no ...` lines are verified heuristically (they cannot be matched by grep) — check manually with `ntn exec <ref> 'show ...'`.

## Test status

Proven end-to-end (not just designed):

| Test | Device | Result |
|---|---|---|
| `add` / `list` / `show` / `exec` / `sync` | a lab Cisco IOS 15.4 router, a lab RouterOS 7.18.2 device | OK |
| `config` + post-check + `check_point` | Cisco — add Loopback99 + description | SUKSES, verified on the device |
| `rollback` | Cisco — remove Loopback99 | SUKSES, `config_list` clean |
| Multi-line `config` (menu path) | RouterOS — `/ip address add` + `set comment` | SUKSES, `mt_normalize` works |
| `rollback` + destructive commands | RouterOS — `remove [find]` + clear comment | SUKSES, MISSING=0 |
| Pre-snapshot guard with unreachable device | fake IP entry | Abort before apply, exit 1 |
| Device-error guard (Cisco) | invalid IP address | GAGAL reported, `config_list` unchanged |
| Device-error guard (RouterOS) | `address=999.999.999.999/24` | `invalid value for argument address`, `config_list` unchanged |

**Not yet tested:** Huawei, Aruba, Arista, Ruijie, Juniper — the code paths exist (`paging_cmd`, `secret_cmd`, `config_enter`, `save_lines`) but have never been run against real devices.

## Technical notes (do not change without testing)

### Two session modes — chosen automatically from the brand

| Brand | Mode | Transport | Pull config | Save |
|---|---|---|---|---|
| Mikrotik | EXEC | `ssh -T`, commands via stdin, no PTY | `/export` | automatic (no `write memory`) |
| Cisco/Aruba/Arista/Ruijie | PTY | `ssh -tt` + paced plan | `show running-config` | `write memory` |
| Huawei | PTY | `ssh -tt` + paced plan | `display current-configuration` | `save` + `Y` (from `system-view`: `return` first) |
| Juniper | PTY | `ssh -tt` + paced plan | `show configuration \| display set` | `commit` **inside** config mode, then `exit configuration-mode` |
| Fortinet | PTY | `ssh -tt` + paced plan | `show full-configuration` | automatic (no save/enable; script lines apply on input) |

`is_exec_brand()` in the engine picks the branch. MikroTik has **no** `configure terminal`, `enable`, `terminal length 0`, or `write memory` — never insert those commands in a MikroTik script.

### Adding a brand — `~/.ntnroute/brands.json`

Per-brand behavior is data, not code: `~/.ntnroute/brands.json` entries override the built-in tables (lowercase brand key). Fields, all optional: `paging`, `secret_cmd`, `config_enter`, `config_leave`, `save_lines` (array; `[]` = no save), `save_delay`, `config_show`, `hostname_show`, `hostname_field` (`hostname`|`sysname`|`host-name`|`colon`), `err_pattern` (ERE), `negate_prefix` (rollback_gen, no trailing space). A brand shipped in `brands.json` ships as `zte` (Cisco-like example — adjust per model). When the user names a vendor that is neither built-in nor profiled: expect generic Cisco-like defaults, the save step is **skipped** with a NOTE, and the right move is to draft a profile (ask for one `show` command output and the device's config-save command), test with `ntn add` + a harmless `ntn config`, then keep the profile in `~/.ntnroute/brands.json` — the installer never overwrites it.

- RouterOS exec-mode is far more reliable than PTY: no banner, paging, or `[admin@host] >` prompt. Commands run sequentially from stdin, separated by newlines. `;` chains also work but one full command per line is easier to read.
- **RouterOS always exits 0 even when a command fails.** Errors are detected from output patterns: `invalid value`, `no such item`, `syntax error`, `expected end of command`, `bad command name`, `ambiguous`, `failure:`. The engine has these patterns in `err_pattern`.
- RouterOS exec-mode **does not keep context between lines**. The menu style `/interface ethernet` then `set [ find ... ]` fails (`expected end of command`) because each line runs as a standalone command. The engine normalizes scripts via `mt_normalize()`: pure path lines are merged into the next line as one full-path command. Write MikroTik scripts with the full path per line, or let the engine merge them — never rely on menu context.
- **Destructive commands cannot be verified automatically.** `remove`/`unset`/`disable`/`reset` remove their own object, so the tokens inside them must NOT appear in the export. Positive-line verification would always fail. The engine marks them UNCHECKED = check manually. Do not read that as a failure.
- **Empty values vanish from `/export`.** `comment=""` produces no token, so it cannot be matched. The engine marks it UNCHECKED, not MISSING. A rollback that clears a comment will always show UNCHECKED=1 — normal.
- RouterOS exec-mode returns **exit 1** when a command is rejected; an older engine message wrongly called this "session dropped". Fixed: auth/disconnect are detected separately, and exit!=0 in exec-mode is treated as a command error with the output content reported.
- MikroTik post-check verification cannot use exact-line grep: `/export` reorders arguments (alphabetically) and folds long lines with `\`. The engine uses `verify_mikrotik`: every `key=value` token in the script is searched as a substring of the export with spaces/quotes/backslashes stripped. Context lines without `=` (e.g. `/ip address`) go to the UNCHECKED list = normal.
- MikroTik hostname from `/system identity print` → the `name:` field. **That name is the device identity, not a misread** — a device can have an identity like `office-router-1` regardless of its board model. Do not "fix" it to the model/board.

### General
- SSH uses the OpenSSH CLI, not paramiko/Python. Sessions use `ssh -tt` with a scheduled (delay-TAB command) plan via stdin; passwords go through `SSH_ASKPASS` + `SSH_ASKPASS_REQUIRE=force`.
- Legacy flags (`diffie-hellman-group14-sha1`, `ssh-rsa`, `aes128-cbc`, `hmac-sha1`) are already wired in so old routers are reachable from OpenSSH 10.
- Interactive Cisco session: `enable` → secret → paging → command → `exit` → `exit`, with per-stage pauses. Command output is captured via `extract_cmd_output` (pattern: command echo, then stop at the `X>` / `X#` prompt).
- `pull_config()` and `pull_hostname()` are the only data-pull paths — mode-aware, used by `add`, `sync`, and `apply_config`. Do not duplicate the logic per brand.
- Applying a config needs a longer lag before `show running-config` (10s) because IOS is still processing.
- The DB is written atomically (temp + `mv`) with `flock`. Never edit `devices.json` with `jq > file` directly — always go through the engine.
- Passwords are stored in plaintext in a mode-600 file. Never print a password in chat without `--reveal` and an explicit user request.
