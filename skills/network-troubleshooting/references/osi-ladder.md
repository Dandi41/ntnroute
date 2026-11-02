# OSI ladder — diagnosis order and symptom map

Master rule: **don't skip layers.** A "no internet" symptom is not a reason to
start at DNS. Drop to the lowest layer not yet proven healthy, prove it, then
climb.

Two moves, used in alternation:

1. **Climb the ladder** (bottom-up) — when you know nothing yet. Confirm L1 is
   healthy, then L2, L3, and so on. Stop at the first layer proven broken.
2. **Bisect** — when the symptom is narrow: "PC A can't reach server B". Find
   the last point that still works and the first point that fails; the problem
   lies between them. Faster than a full ladder climb.

## Symptom map → first layer to check

| Symptom | Start at | Opening question |
|---|---|---|
| Port/link dead, no LED | L1 | Cable, SFP, speed/duplex, is `link-downs` climbing? |
| Link up but no neighbor MAC/ARP | L2 | Right VLAN? Does the trunk carry that VLAN? STP blocking? |
| Can ping the gateway, can't get out | L3 | Is there a route to the destination? Is the next-hop installed in the table? |
| Ping works, TCP to a specific port fails | L4 | Firewall/filter drops? Port listening? MSS/MTU? |
| Ping & TCP work, names don't resolve | L7 | Is the DNS server reachable? Is a resolver configured? |
| Some users slow, others fine | L1/L2 | Are error counters climbing? Duplex mismatch? One saturated link? |
| Intermittent disconnects | L1/L2 | `link-downs`, CRC/input errors, STP topology changes, DHCP lease |
| Only one subnet fails, the rest are fine | L3 | A route specific to that subnet, or an ACL filtering it |

## L1 — Physical / Link

Evidence to look for: link status, speed/duplex, error counters, optical levels.

- A link that is `up/up` does **not** yet mean healthy — rising `input errors`
  and `CRC` mean a cable/fiber problem even though the link is up.
- `link-downs` (RouterOS) or `Last input`/`resets` (IOS) distinguish "dead for
  a while" from "just went down".
- Duplex mismatch: one side `full`, the other `half`/`auto` guessing wrong →
  the classic symptom "small pings fine, large transfers slow/broken".
- Optics: `-inf` or below receiver sensitivity = dirty/broken fiber, not a
  config problem.

Done when: every relevant interface has a clear link status and no error
counter climbs between two readings.

## L2 — Data link / switching

Evidence: MAC table, ARP/neighbors, VLAN membership, STP state.

- An interface in the wrong VLAN = link up but never learning MACs. Check port
  membership (access VLAN / trunk allowed) before blaming the cable.
- No neighbor at all → L2 is broken, not L3. Don't move on to routes.
- STP: a port can be `blocking`/`alternate` — link up, no MACs, and that is
  **normal** when the topology genuinely loops. Check `show spanning-tree`
  before concluding the port is broken.
- ARP incomplete for a host that is alive → check VLAN/port isolation (private
  VLAN, port isolation) and whether the host is really on that segment.

## L3 — Network / routing & addressing

Evidence: the routing table for a **specific destination**, not the whole
table; next-hop ARP; ping to the next-hop.

- `show ip route <destination>` / `/ip route print` — ask "is there a matching
  route?", not "is there a default route?".
- A matching route that is inactive (`A` flag missing on RouterOS, an odd
  `[AD]` on IOS) = unreachable next-hop. Test with a ping to the next-hop.
- The return direction is often forgotten: the packet gets there, but the
  reply has no route back. Test from both sides.
- Wrong NAT/masquerade = outbound works, return doesn't. Check the NAT rules
  for the correct source subnet, not just whether a rule exists.
- Asymmetry: check traceroute in both directions.

## L4 — Transport

Evidence: filter/firewall counters, listening ports, MTU.

- Ping works but TCP fails = very often a firewall drop, not a broken network.
  Check per-rule counters (`/ip firewall filter print stats`,
  `show ip access-lists`).
- MTU/MSS: a large ping with DF fails while small pings work → PMTUD is
  blocked.
- Confirm the port is listening on the server (`ss -lntp`) before blaming the
  network.

## L7 — Application

Evidence: DNS resolution, certificates, HTTP status, application logs.

- DNS: test resolution from the device itself, and ping the resolved IP.
  Resolution works + ping fails = an L3 problem, not DNS.
- Always test twice: once via IP, once via name. The difference points
  straight at DNS.

## Evidence discipline

- One symptom, one active hypothesis. Write down the hypothesis, then the
  command that will prove it — before running anything.
- "Try restarting" is not diagnosis. A restart destroys evidence and often
  hides the cause.
- Take error counter readings **twice** with a pause between them; the
  absolute number means nothing, what matters is that it is **climbing**.
- Record: what you checked, the key output, the conclusion. Without notes, the
  same checks get repeated.
- If a hypothesis is falsified, discard it and write a new one. Don't patch
  the old hypothesis to fit the evidence.
