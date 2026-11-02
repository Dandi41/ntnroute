# Checkpoint → apply → save → verify → rollback

For any change that writes to a device's running config. Steps are in order;
skipping the checkpoint step is what turns a bad line into a rebuild.

## The loop

1. **Snapshot.** Read the full running config and write it to a file named with
   the device IP and a timestamp (`<ip>_pre_<ts>.cfg`). This is the evidence of
   "before", and the human-readable fallback if the generated rollback is wrong.
2. **Generate the rollback script** and store it next to the snapshot *before*
   applying anything. See "Rollback script rules".
3. **Apply** each line in config mode, one send per line, capturing the reply per
   line. A per-line error marker (not the overall exit of the session) is what
   decides success.
4. **Save** with the vendor's save command, then confirm the save output —
   `write memory` prints an address/bytes pair, `copy run start` prints a
   destination confirmation. A silent save is not a verified save.
5. **Re-read the running config** and check every non-trivial line you sent is
   present. Only then does the stored `config_list` get updated with the new
   config.
6. **Roll back** from the stored script if step 3 or 5 failed. Roll back the
   whole script, not just the failing line — a partially applied block is worse
   than either end state.

## Rollback script rules

The rollback is a *derived* artifact, and a naive prefixer gets it wrong:

- A top-level line becomes `no <line>`; a line already starting with `no ` has
  the `no ` removed (that is the undo of a negation).
- A block — a header followed by indented children — cannot be undone line by
  line. Emit the header once, then `no <child>` for each child. Field: never
  emit `no` on the header itself, or you delete the whole parent object instead
  of the added children.
- Skip session-scope commands when generating: `configure terminal`, `end`,
  `system-view`, `return`, `exit`, `commit`. They are navigation, not state.
- A header with no children is a create (`vlan 40`, `ip route …`), so
  `no <header>` is correct there.
- Comment-only content (the running config's `!` separators) is stripped first,
  or the rollback is full of `no !`.

## Error markers per vendor

Treat a reply as failed when it matches any of these, case-insensitively:

- Cisco / Arista / Ruijie / Aruba: `% Invalid input`, `% Incomplete command`,
  `% Ambiguous command`, `% Unrecognized command`, `% Error`.
- Huawei / H3C: `Error:`, `Wrong parameter`, `Too many parameters`,
  `Unrecognized command found`.
- Juniper: `syntax error`, `unknown command`, `statement not found`.
- MikroTik: `syntax error`, `failure:`, `bad command name`.
- FortiGate: `command parse error`, `Unknown action`, `Unknown attribute`.

A `%` at the start of a line is worth treating as an error even without the word
`Invalid` — a rejected command is more often reported than explained.

## Command profiles

| Vendor | Paging off | Show config | Save | Config mode | Privileged |
|---|---|---|---|---|---|
| Cisco IOS | `terminal length 0` | `show running-config` | `write memory` | `configure terminal` | `enable` + secret |
| Arista EOS | `terminal length 0` | `show running-config` | `write memory` | `configure terminal` | already privileged |
| Ruijie | `terminal length 0` | `show running-config` | `write memory` | `configure terminal` | `enable` + secret |
| Huawei VRP | `screen-length 0 temporary` | `display current-configuration` | `save` + confirm `y` | `system-view` | no |
| H3C / Comware | `screen-length disable` | `display current-configuration` | `save force` | `system-view` | no |
| Aruba | `no page` | `show running-config` | `write memory` | `configure terminal` | no |
| Juniper | `set cli screen-length 0` | `show configuration \| display set` | `commit` | `configure` | no |
| MikroTik | none needed | `/export compact` | none (applies on input) | none | no |
| FortiGate | none needed | `show full-configuration` | none (applies on input) | none | no |

Brand strings arrive as whatever the user typed. Normalise case and map
`ios`/`cisco_ios`→cisco, `switch`/`router`→cisco, `vrp`/`datacom`→huawei,
`h3c`/`comware`/`hp`→hp_comware, `ros`/`routeros`→mikrotik before selecting a
profile, and echo the normalised value back so the user sees what was stored.

## Persistent device inventory (surviving session resets)

A model's memory is reset per session; a device list that only lives in the chat
is lost on `/new`. Keep it in one SQLite file outside the session and let every
session read it:

```
devices(id, hostname, ip UNIQUE, port, username, password, secret,
        brand, type, platform,
        config_list,          -- current config as last synced
        check_point,          -- rollback script for the last change
        config_synced_at, last_status, created_at, updated_at)
checkpoints(id, device_id, created_at, reason, applied_script,
            rollback_script, snapshot_path, result)
audit(id, ts, device_id, action, detail)
```

Rules that keep it usable:

- **Never store a device you could not reach.** Test the SSH session, read the
  hostname from the device itself, and only then insert. A reachability retry
  later is cheap; a table full of dead rows poisons every listing.
- **`check_point` is replaced per change, `checkpoints` is append-only.** The
  newest rollback is the one you need fast; the history is what lets you roll
  back two changes instead of one.
- **Resolve device references by id, then IP, then hostname prefix.** Refuse on
  an ambiguous prefix and list the candidates rather than picking one.
- **Mask credentials on every read path** (`***` unless an explicit reveal flag).
  The DB file itself is `chmod 600`.
- **Update `config_list` only after a verified apply** — writing it optimistically
  makes the next rollback target a config the device never had.
- Keep a `backups/` directory of raw config snapshots beside the DB; the DB column
  is for the assistant, the file is for the human.
