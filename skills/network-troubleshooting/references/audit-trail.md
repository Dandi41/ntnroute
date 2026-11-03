# Audit trail — reading it for troubleshooting

The engine writes every config/rollback attempt **before** it touches the device
and settles it afterwards. That makes the trail the one record that survives a
dead session — use it before blaming the transport, the credentials, or the
device.

## Filters

```bash
ntn audit              # last 20 entries, all actions
ntn audit 50           # last 50
ntn audit pending      # attempts with NO verdict at all
ntn audit failed       # every failure (add/sync/config/rollback), newest last
ntn audit config 50    # config + rollback lifecycle only
ntn audit all 100      # everything, last 100
```

## Action vocabulary

| Action | Meaning | What it tells you |
|---|---|---|
| `config-pending` / `rollback-pending` | Written before apply; **never settled** | The process died mid-apply — device state is UNKNOWN |
| `config-started` / `rollback-started` | The same entry, settled later | An attempt happened at that timestamp; it reached a verdict |
| `config-ok` | Applied and verified | Every script line reached the running-config |
| `config-failed` | Rejected or unverified | Device error output is in the transcript; `config_list` unchanged |
| `config-aborted` | Died before/while applying | Pre-snapshot guard fired or the session was cut |
| `rollback` | Rollback succeeded | `check_point` was consumed |
| `sync`, `sync-failed` | Config pull | Baseline availability |
| `add`, `add-failed` | Inventory change | Who registered what, when |
| `remove` | Device removed | — |

## Troubleshooting procedure

1. `ntn audit pending` — anything here means an apply died mid-flight and the
   device may not match the inventory's `config_list`. **Verify the live config
   before trusting anything in the inventory.**
2. `ntn audit failed` — the failure history: repeated `sync-failed` means
   reachability/auth, `config-failed` means a rejected script.
3. `ntn audit config 50` — the change timeline: did someone change this device
   shortly before the outage started? Was there an attempted change that never
   reported a verdict?
4. Only then continue with `ntn ping` / `ntn exec` and the OSI ladder.

## Recovering from an unsettled attempt

An unsettled entry plus a `config-aborted` counterpart means "attempted, outcome
unknown". Recover in this order:

1. `ntn exec <ref> '<show running-config | include ...>'` — read what is
   actually configured now.
2. Compare against the newest pre-change snapshot in `~/.ntnroute/backups/`
   (`<hostname>-<ts>-pre.cfg`) to see what the attempt may have changed.
3. If a `check_point` still exists (`ntn show <ref>`), `ntn rollback <ref>`
   restores the pre-change state.
4. If the device is unreachable, treat it as an outage: this skill's early
   layers (L1/L2, management path) come first.

## What the trail does NOT contain

- Command output (that is in `~/.ntnroute/backups/*.cfg` snapshots and the
  `ntn exec` transcripts).
- Reads: `list`/`show`/`exec` are not audited — only inventory and config
  changes are.
- Retention: the trail keeps the newest 500 entries; older ones are dropped.
