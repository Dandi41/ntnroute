# NTnRoute.AI

[English](README.md) | [Indonesia](README.id.md) | [Español](README.es.md) | [日本語](README.ja.md) | [Deutsch](README.de.md)

SSH-based network device engine for AI agents: a small device inventory, safe CLI execution, config backup, and **gated** config changes with automatic rollback — plus a set of [Hermes Agent](https://hermes-agent.nousresearch.com) skills that teach the agent how to drive it responsibly.

## What it does

- **Inventory** — register devices once (`ntn add`); the engine tests the SSH connection, pulls the hostname and running config, and only then saves. Stored in a plain JSON file (`~/.ntnroute/devices.json`, mode 600) that survives agent restarts.
- **Read-only access** — `ntn exec` runs `show ...` style commands and returns the transcript.
- **Config backup** — `ntn sync` pulls the running config into the inventory and a timestamped backup file.
- **Gated config changes** — `ntn config` performs: pre-change snapshot → apply → save → post-check (every script line must appear in the new config) → inventory update. Unreachable device before the change? It aborts. Device rejects a line? It reports failure and leaves the inventory untouched.
- **Rollback** — every change stores a checkpoint; `ntn rollback` applies the stored undo script.
- **Audit trail** — `ntn audit` shows the last operations.

No Python, no agents, no daemons: **bash + jq + OpenSSH** only.

## Supported platforms

| Vendor | Mode | Config pull | Save |
|---|---|---|---|
| Cisco IOS | interactive PTY | `show running-config` | `write memory` |
| Huawei | interactive PTY | `display current-configuration` | `commit` |
| Aruba / Arista / Ruijie / Juniper | interactive PTY | vendor equivalent | vendor save |
| MikroTik RouterOS | exec-mode (`ssh -T`) | `/export` | automatic |

Legacy crypto (old Cisco images) is handled: `diffie-hellman-group14-sha1`, `ssh-rsa`, `aes128-cbc`, `hmac-sha1` are negotiated when needed.

## Install

Requirements: Linux/macOS with `bash`, `jq`, `ssh` (OpenSSH).

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

## Quick start

```bash
# register a device (connection is tested first; nothing saved on failure)
ntn add 10.0.0.5 22 admin S3cr3t! Router Cisco enablepass123

ntn list                # numbered inventory
ntn show 1              # details + stored config
ntn ping 1              # ICMP check
ntn exec 1 'show ip interface brief' 'show ip route'
ntn sync all            # pull running-config for every device
ntn audit 10            # last 10 operations
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

- Passwords are stored **in plaintext** in `~/.ntnroute/devices.json` (mode 600, owner-only). That is a deliberate trade-off for a lab tool — do not point it at production if that is unacceptable.
- `ntn show <ref>` masks passwords by default; `--reveal` prints them.
- `devices.json` and `backups/` are gitignored. **Never commit them.**

## Status & honesty

Proven end-to-end against real devices: Cisco IOS 15.4 and MikroTik RouterOS 7.18.2 (add/list/show/exec/sync, config + post-check, rollback, destructive commands, unreachable-device guard, device-error guard).

The code paths for Huawei, Aruba, Arista, Ruijie and Juniper exist but have **not** been exercised against real hardware yet — treat them as experimental and report issues.

## License

[MIT](LICENSE) © Dandi Suryadi
