# Diagnosis playbook — step by step

Eight phases, each with an exit condition. The OSI ladder
(`references/osi-ladder.md`) is the reasoning model; this file is the order of
operations you actually execute.

Non-negotiable during a diagnosis: **read-only**. No `set`, `configure`, `no`,
`undo`, `clear`, `reset`, `shutdown`, `reload`, `reboot`. A restart destroys
the evidence you need and usually hides the cause.

---

## Phase 0 — Scope the symptom

One compact question, recorded in writing before touching anything:

```
Device:    <ref>
Symptom:   what is actually wrong, in the observer's words
Since:     timestamp or "always / unknown"
Scope:     one host / one subnet / one site / everywhere
Changed:   did anything change recently — config, cabling, ISP, power, firmware
Access:    does it affect your management path to this device
```

Exit condition: you can state the symptom in one sentence without hedging, and
you know whether your own access is at risk.

If `Changed: yes` or `Access: yes`, read `references/audit-trail.md` before
anything else — a change that never reported a verdict means the live state is
unknown, and that reframes every observation that follows.

---

## Phase 1 — Is it there at all?

Establish reachability before interpretation:

```bash
NTN_INTERNAL=1 ntn ping <ref>
```

Ping failure is **one signal, not a verdict**. Three very different situations
look identical from here:

- device down / path down → real outage
- ICMP filtered by policy → device is fine, your probe is blocked
- your session or source network is broken → not the device's problem

Distinguish them with a second vantage point: another device in the inventory
that sits on the same segment, or the device's own logs if you can still reach
it another way. If reachability is genuinely ambiguous, report exactly that
ambiguity instead of guessing.

Exit condition: `reachable` / `unreachable-and-confirmed` /
`unreachable-but-ambiguous`. Everything downstream differs by which.

---

## Phase 2 — Capture a baseline

```bash
ntn sync <ref>        # snapshot the running config
NTN_INTERNAL=1 ntn exec <ref> '<identity command>'
```

Identity command per platform is in Phase 1 of
`network-security-audit/references/audit-playbook.md`. You need exact OS and
version now, because it decides which diagnostic commands are even valid.

If the device is unreachable over SSH but answers ICMP: skip to Phase 3 and
work from an upstream neighbour's view. A snapshot you cannot take is itself a
finding — say so.

Exit condition: config snapshot saved (or its absence explained), platform
confirmed.

---

## Phase 3 — Read state, don't guess

Run **one batch per device**, save the raw transcript to a file. Batch by
layer, not by convenience:

```bash
NTN_INTERNAL=1 ntn exec <ref> \
  '<L1 cmd>' '<L1 cmd>' '<L1 cmd>' \
  '<L2 cmd>' '<L2 cmd>' \
  '<L3 cmd>' '<L3 cmd>' '<L3 cmd>' \
  > /tmp/<host>-diag-$(date +%Y%m%d-%H%M%S).txt
```

Per-platform commands: `references/vendor-commands.md`. Those are starting
points for confirmed syntax, not a canonical registry — if a command is
rejected, check official docs before inventing an alternative. A rejected
command is not a fault.

Start from the layer the symptom map points at. Do not run the full ladder
"to be thorough" — most of it will be noise, and noise competes with signal.

Exit condition: raw output saved for every layer you need to judge.

---

## Phase 4 — Apply the ladder

Work `references/osi-ladder.md`. Two moves, alternating:

- **Climb** when you know nothing: L1 → L2 → L3 …, stop at the first layer
  proven broken.
- **Bisect** when the symptom is narrow: find the last working point and the
  first failing point. The fault is between them.

Per layer, the discipline is the same:

1. State the hypothesis in one sentence.
2. Name the command that will prove or kill it — before you run it.
3. Run it. Read the result.
4. If falsified, discard the hypothesis entirely. Do not patch it to fit.

Layer-specific traps are in `osi-ladder.md`. The three that cost the most time:

- A link that is `up/up` is not necessarily healthy — rising CRC/input errors
  mean a physical problem with a green light on it.
- ARP incomplete for a live host is L2 (VLAN / port isolation), not L3.
- Ping works but TCP to one port fails is almost always a filter or a
  non-listening service, not a broken route.

Exit condition: one layer identified as broken, or an explicit statement that
all checked layers are healthy and the fault is elsewhere.

---

## Phase 5 — Counters need two readings

Any counter-based hypothesis (errors, drops, flaps, retransmits, CPU) needs a
second reading with a real pause between them — minutes, not seconds.

```bash
NTN_INTERNAL=1 ntn exec <ref> '<counter cmd>'    # reading 1
sleep 120
NTN_INTERNAL=1 ntn exec <ref> '<counter cmd>'    # reading 2
```

Absolute values are archaeology: a CRC count of 42 since last year is history.
**Climbing** is a fault. Flat is not. Write both numbers and the interval into
your notes, because "counters are fine" without numbers is not evidence.

Exit condition: every counter claim is either "flat over N minutes" or
"climbing at roughly X per N minutes".

---

## Phase 6 — Only then research

When the hypothesis is still unconfirmed, go external — but in this order:

1. Vendor official documentation for that exact platform and release.
2. Vendor bug/CVE advisories and release notes (a known bug in that version is
   a legitimate root cause).
3. Community and forums — for leads only, verified against (1) before it enters
   the report.

`references/official-sources.md` lists the sources per vendor. Use
`web_search` and `web_extract`.

Exit condition: either the hypothesis is confirmed, or you can state the
remaining unknown precisely enough that the next test is obvious.

---

## Phase 7 — Report and propose

Deliver, in this order:

```
Symptom:      <one sentence, observer's words>
Scope:        <who/what is affected>
Checked:      <layers and specific checks, with evidence excerpts>
Confirmed:    <facts only>
Hypothesis:   <leading cause + confidence: high/medium/low>
Ruled out:    <what you disproved and by what evidence>
Unknown:      <what still isn't established>
Next test:    <the single cheapest step that would settle it>
Proposed fix: <if cause is confirmed>
```

Rules for this report:

- Never present an unconfirmed guess as root cause.
- Ruled-out items belong in the report — they stop the next person repeating
  your work.
- The proposed fix is a proposal. Applying it is `network-change-management`,
  with its plan approval and rollback.

Exit condition: the user has the report. Stop there.

---

## When it's an outage, not a puzzle

If the device is down and staying down, the priority order changes:

1. Restore service, then diagnose. But note what you did and when — a restart
   during an outage is a legitimate emergency action, and its cost is the
   evidence it destroys.
2. Protect the management path explicitly. Never change the interface carrying
   your session.
3. If a rollback is available and the symptom started right after a change,
   propose the rollback through `network-change-management` rather than
   hand-fixing live. The stored `check_point` exists exactly for this.

---

## Fleet symptoms

"Everything is slow" is not a device diagnosis. Before per-device work,
separate the cases:

- one device's counters climbing → local L1/L2 fault
- all devices behind one uplink → upstream fault, test from the edge outward
- switching-path failures across a segment → L2 loop or STP event; check
  topology-change counters and root bridge stability
- DNS-shaped ("nothing resolves, but IPs work") → L7, and usually not the
  device you started on

Diagnose at the boundary where behaviour changes, not at the device that
happens to be in the inventory.

---

## Quick reference — which skill owns what

| Situation | Skill |
|---|---|
| Unreachable, slow, flapping, errors | this playbook |
| "Is this device secure?" | `network-security-audit` |
| "Change this setting" | `network-change-management` |
| "Add or remove a device" | `ntnroute` |
| "How do I SSH in manually" | `network-device-cli` |