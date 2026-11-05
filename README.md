# NTnRoute.AI

[English](README.md) | [Indonesia](README.id.md) | [Español](README.es.md) | [日本語](README.ja.md) | [Deutsch](README.de.md)

SSH-based network device engine for AI agents: a small device inventory, safe CLI execution, config backup, and **gated** config changes with automatic rollback — plus a set of [Hermes Agent](https://hermes-agent.nousresearch.com) skills that teach the agent how to drive it responsibly.

## What it does

- **Inventory** — register devices once (`ntn add`); the engine tests the SSH connection, pulls the hostname and running config, and only then saves. Stored in a plain JSON file (`~/.ntnroute/devices.json`, mode 600) that survives agent restarts.
- **Read-only access** — the engine runs `show ...` style commands on demand and returns the transcript.
- **Config backup** — `ntn sync` pulls the running config into the inventory and stores a timestamped snapshot; every successful change (and rollback) publishes an archive pair under `~/.ntnroute/backups/<host>/<YYYY-MM>/`. Each month folder holds up to 4 change pairs and 4 sync/add snapshots, kept for the last 3 months plus one yearly keeper; loose files from older versions are filed into this layout automatically.
- **Gated config changes** — `ntn config` performs: pre-change snapshot → apply → save → inventory snapshot/archive refresh. It fails only on a device-side command error, lost session, or unavailable pre-change snapshot. Functional success is confirmed afterward with planned read-only device checks.
- **Rollback** — every change stores a checkpoint; the stored undo script can be replayed on request.
- **Audit trail** — every config/rollback attempt is logged *before* it touches the device (`config-pending`), then settled: `config-ok`/`config-failed`/`config-aborted` + a `config-started` marker for the record. the change log's filters serve troubleshooting and security review: `pending` (attempts with no verdict at all — a process killed mid-apply), `failed`, `config`, `all`. Entries older than 105 days are pruned automatically; security-audit runs are recorded separately, only when an audit is actually performed.

The engine is bash + jq + OpenSSH only — no Python, no agents, no daemons. The
helper scripts (`triage`, `rollback_gen`, `ios_session.sh`) are bash + awk too;
only the security-audit tooling (`cfg_audit.py`, `sec_audit.py`) uses stdlib Python.

## Supported platforms

| Vendor | Mode | Config pull | Save |
|---|---|---|---|
| Cisco IOS | interactive PTY | `show running-config` | `write memory` |
| Huawei VRP | interactive PTY | `display current-configuration` | `save` + confirm |
| Aruba / Arista / Ruijie | interactive PTY | `show running-config` | `write memory` |
| Juniper Junos | interactive PTY | `show configuration \| display set` | `commit` (inside config mode) |
| Fortinet FortiGate | interactive PTY | `show full-configuration` | automatic (applies on input) |
| MikroTik RouterOS | exec-mode (`ssh -T`) | `/export verbose` | automatic |
| Linux (SSH) | exec-mode (`ssh -T`) | `uname -a` + os-release snapshot | — (no config model) |
| Windows (OpenSSH, cmd.exe) | exec-arg (`ssh host "cmd"`) | `systeminfo` snapshot | — (no config model) |

Legacy crypto (old Cisco images) is handled: `diffie-hellman-group14-sha1`, `ssh-rsa`, `aes128-cbc`, `hmac-sha1` are negotiated when needed.

## Adapting to new vendors

Per-brand behavior lives in `~/.ntnroute/brands.json` — edit it to support a vendor the engine doesn't know, or to override a built-in (firmware changes included). One entry is enough:

```json
{
  "zte": {
    "paging": "terminal length 0",
    "config_enter": "configure terminal",
    "config_leave": "end",
    "save_lines": ["write memory"],
    "config_show": "show running-config",
    "hostname_show": "show running-config | include hostname",
    "hostname_field": "hostname",
    "err_pattern": "(^%|Invalid input)"
  }
}
```

Fields: `paging`, `secret_cmd`, `config_enter`, `config_leave`, `save_lines` (array), `save_delay`, `config_show`, `hostname_show`, `hostname_field` (`hostname`|`sysname`|`host-name`|`colon`), `err_pattern` (grep -E), `negate_prefix` (used by `rollback_gen`). Unknown brands without a profile get generic Cisco-like defaults and skip the save step. The installer never overwrites your `brands.json`.

## Device database format

The inventory lives in `~/.ntnroute/devices.json` (mode 600, gitignored — never commit the real one). The engine reads and writes an exact shape: `next_id`, `devices[]`, `checkpoints[]`, `audit[]`, `security_audits[]`. See [`examples/devices.example.json`](examples/devices.example.json) for a filled-in reference with placeholder credentials — point any AI agent or script at that file so it writes the same field names instead of inventing its own.

## Install

Requirements: Linux, macOS, or Windows (via Git for Windows) with `bash`, `jq`, `ssh` (OpenSSH). macOS needs GNU coreutils for `timeout` (`brew install coreutils`).

```bash
git clone https://github.com/Dandi41/ntnroute.git
cd ntnroute
./install.sh
```

The installer:

1. checks `jq` and `ssh`,
2. installs the engine to `~/.ntnroute/ntn` (mode 700) and symlinks it as `~/.local/bin/ntn`,
3. creates `~/.ntnroute/` with an empty inventory (mode 600),
4. if you use [Hermes Agent](https://hermes-agent.nousresearch.com), copies the five skills into `~/.hermes/skills/networking/`.

### Windows (native, no WSL)

NTnRoute also runs natively on Windows through Git for Windows (MSYS2 bash) — no WSL needed.

1. Install [Git for Windows](https://git-scm.com/download/win) — it bundles `bash` and OpenSSH `ssh`.
2. Open **Git Bash** and run:

```bash
git clone -b beta https://github.com/Dandi41/ntnroute.git ~/ntnroute
cd ~/ntnroute
bash install.sh
```

On Windows the installer detects MSYS2 automatically: the engine goes to `~/.ntnroute/ntn`, `ntn` is placed in `~/.local/bin` as a copy (Windows symlinks need privileges), and if `jq` is missing it downloads `jq.exe` into `~/.ntnroute/bin` (the engine adds that directory to `PATH` itself at runtime). If the shell cannot find `ntn` after installing, add `~/.local/bin` to your PATH as the installer suggests. Every command behaves exactly as on Linux/macOS; interactive vendor sessions run over the MSYS2 PTY. Windows support lives on the `beta` branch until it is merged.

## Quick start

If you are unsure how to use the NTnRoute engine, type `ntn` or `ntn help` to your agent. The agent will show the available menu and guide the appropriate workflow.

```bash
# register a device (connection is tested first; nothing saved on failure)
ntn add 10.0.0.5 22 admin S3cr3t! Router Cisco enablepass123

# inventory and configuration-summary menu
ntn list
ntn add <IP> <Port> <User> <Pass> <Type> <Brand> [Secret]
ntn remove <number|id>
ntn show <ref>
ntn sync <ref|all>
```

A config change is always: plan → approval → apply → verify. The bundled `network-change-management` skill enforces the approval gate and generates the rollback script before anything touches the device.

## The skills

| Skill | Purpose |
|---|---|
| `ntnroute` | Core workflow rules for the `ntn` engine (inventory, exec, config, rollback) |
| `network-device-cli` | SSH session mechanics per vendor, legacy crypto, credential parsing |
| `network-change-management` | Plan/approval gate, blast-radius audit, rollback generation |
| `network-troubleshooting` | OSI-first diagnosis with vendor command references |
| `network-security-audit` | Local hardening + perimeter audit of device configs |

## Security notes

- Passwords are stored **in plaintext** in `~/.ntnroute/devices.json` (mode 600, owner-only). Guard that file well so it never spreads beyond the machine.
- `ntn show <ref>` masks passwords by default.
- Config backups under `~/.ntnroute/backups/` contain the same device secrets — treat them with the same care.
## Status & honesty

Proven end-to-end against real devices: Cisco IOS 15.4 and MikroTik RouterOS 7.18.2 (add/list/show/exec/sync, config + post-check, rollback, destructive commands, unreachable-device guard, device-error guard). The other brands (Huawei VRP, Arista EOS, Aruba AOS-CX, Ruijie RGOS, Juniper Junos, Fortinet FortiGate) are verified the same way against emulated vendor CLIs (local test harness, not part of the toolkit).

The code paths for Huawei, Aruba, Arista, Ruijie and Juniper exist but have **not** been exercised against real hardware yet — treat them as experimental and report issues.

## Support

If ntnroute saves you time, you can buy the creator a lemper 🙂 — an Indonesian sticky-rice snack: **[tako.id/Lemper41](https://tako.id/Lemper41)**

Find me on [Instagram](https://www.instagram.com/sdandi_41/) and [LinkedIn](https://www.linkedin.com/in/dandi-suryadi-a29276253/).

## License

[MIT](LICENSE) © Dandi Suryadi
