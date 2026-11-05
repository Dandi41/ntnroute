# Configuration Change Plan Template

Fill this in before touching the device, present it to the user, then stop and
wait for a reply. Write it in plain language first, with the exact commands
right after.

---

**Device:** `<ref>` — `<hostname>` `<ip:port>` `<brand>`
**Risk:** the agent's own assessment — what could break, which lines carry it, why acceptable
**Baseline:** `~/.ntnroute/backups/<synced-file>.cfg`

### 1. Plan + rationale

One plain-language sentence: what changes and why. Example: "Ethernet0/4 will
be enabled as the uplink to the second-floor switch so VLAN 40 can pass."

Technical: the interfaces/VLANs/objects touched, and what is **not** touched.

### 2. Configuration to be applied

```text
<contents of change.cmd exactly as-is>
```

### 3. Rollback

```text
<contents of rollback.cmd exactly as-is, including TODO lines filled from the pre-change snapshot>
```

### 4. Post-apply verification

Read-only command + expected result:

```text
<verification command, e.g. show ip interface brief>
```

Expected: `<token/state, e.g. Ethernet0/4 ... up ... up>`.
If what comes back is not this → report it as-is, do not patch it with an
unplanned change.

### 5. Risk

- Lines that carry risk (especially the management path) + why they are still safe:
  - `line 2: description only` → cosmetic, does not change forwarding.
- Management path: `<ip>` via `<iface>` — untouched.
- Impact window: `<e.g. brief link-down during no shutdown>`.
- Rollback point: `ntn rollback <ref>` (checkpoint `<id>`), or push script (3).

---

**Awaiting approval.** Without an explicit reply, nothing is sent to the device.
