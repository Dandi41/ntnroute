# Audit trail — reading it for troubleshooting

The engine writes every config/rollback attempt **before** it touches the device
and settles it afterwards. That makes the trail the one record that survives a
dead session — use it before blaming the transport, the credentials, or the
device.

## Filters

Run every `ntn audit`/`ntn exec`/`ntn rollback` call below with the
`NTN_INTERNAL=1` prefix (the engine refuses them without it).

```bash
NTN_INTERNAL=1 ntn audit              # last 20 entries, all actions
NTN_INTERNAL=1 ntn audit 50           # last 50
NTN_INTERNAL=1 ntn audit pending      # attempts with NO verdict at all
NTN_INTERNAL=1 ntn audit failed       # every config/rollback failure, newest last
NTN_INTERNAL=1 ntn audit config 50    # config + rollback lifecycle only
NTN_INTERNAL=1 ntn audit all 100      # everything, last 100
```

## Action vocabulary

| Action | Meaning | What it tells you |
|---|---|---|
| `config-pending` / `rollback-pending` | Written before apply; **never settled** | The process died mid-apply — device state is UNKNOWN |
| `config-started` / `rollback-started` | The same entry, settled later | An attempt happened at that timestamp; it reached a verdict |
| `config-ok` | Device accepted the apply | Run the planned read-only checks to establish functional success |
| `config-failed` | Device rejected commands or the session failed | Device error output or transport failure is in the transcript |
| `config-aborted` | Died before/while applying | Pre-snapshot guard fired or the session was cut |
| `rollback` | Rollback succeeded | `check_point` was consumed |
| `rollback-failed` | Rollback apply rejected | The undo script did not land; snapshots are still in `~/.ntnroute/backups/` — investigate before retrying |

## Retention

The change log is pruned on **every write**: entries older than **105 days**
are deleted immediately, the log is capped at 500 entries, and only
config/rollback lifecycle actions are kept at all. `*-pending` entries never
age out — an unresolved pending is exactly the artifact you must see.

## Troubleshooting procedure

1. `ntn audit pending` — anything here means an apply died mid-flight and the
   device may not match the inventory's `config_list`. **Verify the live config
   before trusting anything in the inventory.**
2. `ntn audit failed` — the failure history: `config-failed`/`rollback-failed`
   mean a rejected script. (Sync/add attempts are not logged — reachability
   history comes from the device itself, not the trail.)
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
