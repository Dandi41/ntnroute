# Routing protocol interop — when adjacency is Full and routes still vanish

Multi-vendor routing fails in a specific class of ways that produce **no error
message and no adjacency flap**. Both devices report healthy, the neighbour is
`Full`, and traffic still black-holes. This file records those failure modes,
because they cost hours and every one of them was reproduced on live equipment.

Scope: OSPF primarily, with notes on the general pattern that transfers to
IS-IS and BGP.

---

## The cardinal rule

**`Full` adjacency is not convergence.** An adjacency proves the hello/
database-exchange handshake succeeded. It says nothing about whether the
neighbours agree on how the *link* behaves — and a disagreement there makes
the SPF computation discard routes that were successfully exchanged.

When routes are missing despite `Full` adjacency, the problem is almost always
in one of these four places:

1. network type mismatch (broadcast vs point-to-point)
2. MTU mismatch
3. area / stub / NSSA disagreement
4. authentication or key mismatch on one direction only

---

## Failure mode 1 — OSPF network type mismatch (the silent killer)

### What happened on live equipment

Cisco side: default `broadcast` network type on a `/30` link → DR/BDR election.
MikroTik side: template used `type=ptp` on the same link → no DR.

Result:

- Adjacency: `FULL/BDR` on the Cisco side, `Full` on RouterOS. Looks fine.
- Cisco logs/database: the RouterOS Router-LSA is marked
  **`not-reachable in topology Base with MTID 0`**
- Every route learned through that neighbour is dropped.
- No syslog error, no adjacency drop, no counter anomaly. Traffic just dies.

That message is the tell. `not-reachable in topology Base` means SPF could not
place the advertising router's transit link in the topology, so it treats the
whole LSA as unreachable — and silently discards it.

### Why it happens

A `broadcast` segment expects a DR and a type-2 (network) LSA. A
`point-to-point` segment has no DR and uses type-1 LSAs with a different link
description. When two neighbours disagree, both describe the same wire
differently, and the SPF tree cannot reconcile them.

### Fix

Make both sides agree. On a `/30` or `/31` point-to-point link, the correct
answer is point-to-point on both:

```
! Cisco IOS — interface facing the RouterOS neighbour
interface Ethernet0/0
 ip ospf network point-to-point
```

```
# RouterOS — the interface belongs to the OSPF instance, no DR wanted
/routing ospf interface-template add interfaces=ether1 type=ptp area=backbone
```

Verification after the change: the Cisco neighbour line shows `FULL/ -`
(the dash means "no DR/BDR role"), and the previously-missing routes appear
in `show ip route ospf`.

If the link genuinely is a multi-access segment (a switch between more than
two routers), the opposite fix applies: make the odd one out `broadcast`, and
verify the DR election lands where you intended.

### Generalisation

This is not an OSPF quirk. Any protocol where the *link model* is negotiated
per-interface rather than per-neighbour has the same class of bug: IS-IS
point-to-point vs broadcast, BGP multihop vs directly-connected. When routes
disappear with everything "up", compare the link model on both ends before
comparing anything else.

---

## Failure mode 2 — RouterOS `passive` is a flag, not a parameter

```
# WRONG — RouterOS rejects this
/routing ospf interface-template add interfaces=ether3 passive=yes

# RIGHT
/routing ospf interface-template add interfaces=ether3 passive
```

`passive` takes no value. The rejection is easy to miss when a template is
applied as part of a batch: the interface silently never enters OSPF, the
connected subnet is never advertised, and remote routers simply never learn it.
Locally everything looks configured because the interface exists and has an
address.

Symptom shape: one subnet missing from every other router's table, adjacency
healthy everywhere, no logs. Check `passive` first on the interface that owns
the missing subnet.

---

## Failure mode 3 — MTU mismatch inside an adjacency

OSPF will form an adjacency across an MTU mismatch and then behave erratically,
because a full-size DBD or LSA update cannot cross. Cisco logs an explicit
warning when it notices:

```
%OSPF-5-ADJCHG: Nbr 10.0.0.2 on Ethernet0/0 from DOWN to INIT, ...
%IPV4_OSPF-4-MTU_MISMATCH: ...
```

Check MTU explicitly on both ends (`show interfaces` / `/interface print`
or `/interface ethernet print`). Do not assume an inherited default matches.

Fix: align the MTU, or set `ip ospf mtu-ignore` on Cisco as a workaround while
the real MTU difference is resolved. The workaround hides fragmentation
problems rather than fixing them — treat it as temporary.

---

## Failure mode 4 — asymmetric authentication

One side authenticates, the other does not. The adjacency may briefly reach
`EXCHANGE` and drop, or in some combinations never leave `INIT`. The important
detail: **check both directions**, not just the side you configured. A
mismatched key on one interface produces the same log line as a totally absent
configuration, so read both configs before changing anything.

---

## Failure mode 5 — area / stub / NSSA disagreement

A stub area on one side, normal area on the other: the adjacency forms, and
then no external routes are propagated to the stub side. The neighbours agree
about everything except what the area is allowed to carry.

Verify area type on both ends (`show ip ospf interface` /
`/routing ospf area print`), and remember that `NSSA` and `stub` are different
and mutually exclusive.

---

## Redistribution traps worth knowing

- **Redistributing into OSPF without a metric** — the route enters with the
  default metric and may be treated as unreachable or as a worse path than
  intended. Always set an explicit metric.
- **Redistributing the same prefix at two points** — unless you control the
  metric, you get asymmetric paths and intermittent failures that look like
  link flapping.
- **Filtering redistribution on one router only** — the other still advertises.
  Loop prevention that is not symmetric is not loop prevention.
- **`always`-type default-originate** — injects a default even when the
  upstream is dead. Convenient in the lab, an outage amplifier in production.

---

## Rollback generation and routing changes

`rollback_gen` negates changes by injecting the vendor's negation prefix
(`no`, `undo`, `delete`). That model is correct for most configuration, and
wrong for routing in one dangerous way:

**It will inject `shutdown` into an interface that was previously `up`**, if
the change script created or modified that interface. Applying that rollback
turns a working link into a dead one — the opposite of a rollback's purpose.

Before applying a generated rollback that touches interfaces or routing
processes:

1. Read the generated script line by line. Do not trust it because it was
   generated.
2. Any `shutdown` / `disable` on an interface carrying a routing adjacency is
   a stop sign.
3. For routing and interface changes, **write the rollback by hand** and keep
   the generated one as reference only.
4. Verify the rollback path does not cross the management interface.

This is a property of the negation model, not a bug that will be fixed: a
line-based negator cannot know that `ip ospf network point-to-point` is
"remove this line", while creating `interface X` is "delete the interface", and
deleting an interface is `shutdown`.

---

## Diagnostic order for "adjacency Full, routes missing"

```
1. show ip ospf neighbor / /routing ospf neighbor print
     → is it FULL/ - or FULL/BDR? The role tells you the link model.
2. show ip ospf database / /routing ospf lsa print
     → is the remote Router-LSA present, and is it flagged unreachable?
3. Compare interface network type on both ends.
4. Compare MTU on both ends.
5. Compare area type (stub/NSSA) on both ends.
6. Compare authentication config on both ends.
7. Only now look at filters, distribute-lists, and redistribution.
```

Steps 1–2 usually settle it in under a minute. The mistake is starting at
step 7 because "the adjacency is up, so it must be a policy problem".

---

## Verified on

Lab topology, four routers, OSPF area 0:
Cisco IOS 15.x ×2, RouterOS 7.18.x ×2, `/30` interconnects, two LAN segments
served by DHCP.

- Failure mode 1 reproduced live: `FULL/BDR` on Cisco, `not-reachable in
  topology Base with MTID 0`, all RouterOS routes discarded. Fixed with
  `ip ospf network point-to-point` on both Cisco interfaces facing RouterOS.
  After the fix: `FULL/ -`, full routing table on all four, end-to-end ping
  5/5 to both LANs from both sides.
- Failure mode 2 reproduced live: `passive=yes` rejected by RouterOS, LAN
  subnet never advertised, fixed by the bare `passive` flag.
- The `rollback_gen` interface-shutdown caveat was identified on the same run
  and the rollback was written by hand instead.