#!/usr/bin/env python3
"""Reads `show` output captured from a device and reports findings by OSI layer.

It never touches a device. You capture, it reads:

  ntn exec 1 'show interfaces' 'show ip route' 'show ip arp' > out.txt
  triage.py out.txt --mgmt-ip 10.0.0.5

  ntn exec 3 '/interface print detail' '/ip route print' > out3.txt
  triage.py out3.txt --mgmt-ip 10.0.0.6

Multiple files are fine. Block type is detected from the text, so mixed captures
in one file also work. Vendor is detected the same way.

Exit 1 when a layer-1/2 finding is present that a config change cannot fix
(cabling, duplex, errors climbing) — that is the "stop, this is hardware" gate.
Exit 0 otherwise.

Counter warning: absolute error counts prove nothing. Re-capture after traffic
and diff; the tool prints the numbers so you can compare, and says so.
"""
import argparse
import re
import sys

SEV = {"CRIT": 0, "WARN": 1, "INFO": 2}


def findings_new():
    return []


def add(f, sev, layer, rule, why, ev=""):
    f.append((sev, layer, rule, why, ev.strip()))


# ------------------------------------------------------------------ detection
def detect(text):
    if re.search(r"^Flags:.*R - running|^/interface|^\s*\d+\s+[RX ]+\s+name=", text, re.M):
        return "mikrotik"
    return "cisco"


def blocks(text):
    """Return list of (kind, text) by sniffing known headers."""
    out = []
    # Cisco: split on the echoed prompt command line is unreliable; split on
    # recognizable section starts instead.
    for m in re.finditer(r"^(show \S+.*|/[\w/\- ]+)$", text, re.M):
        pass
    parts = re.split(r"(?m)^(?=(?:show |/)[\w/\- ]+$)", text)
    for p in parts:
        body = p.split("\n", 1)[1] if "\n" in p else ""
        head = p.split("\n", 1)[0].strip()
        if not head:
            continue
        out.append((head, p))
    return out


# ---------------------------------------------------------------------- cisco
CISCO_IFACE = re.compile(r"^(\S+) is (up|down|administratively down), line protocol is (up|down)", re.M)


def parse_cisco(text, f, mgmt_ip):
    hits = list(CISCO_IFACE.finditer(text))
    for idx, m in enumerate(hits):
        name, admin, proto = m.group(1), m.group(2), m.group(3)
        start = m.start()
        # slice to the next interface header by match position — searching for the
        # header text misses when spacing/prefix differs between captures
        end = hits[idx + 1].start() if idx + 1 < len(hits) else len(text)
        chunk = text[start:end]

        if admin == "administratively down":
            add(f, "WARN", "L1", "iface-admin-down",
                f"{name}: shut by config — link will never come up until `no shutdown`", name)
        elif proto == "down":
            add(f, "CRIT", "L1", "iface-protocol-down",
                f"{name}: link up but line protocol down — cabling/SFP/speed mismatch, or "
                f"peer not enabled. Config alone cannot fix this", name)

        def num(label):
            mm = re.search(rf"^\s*(\d+) {label}\b", chunk, re.M)
            return int(mm.group(1)) if mm else 0

        errs = num("input errors")
        crc = num(r"CRC")
        resets = num(r"interface resets")
        late = num(r"late collision|late collisions")
        drops = num(r"Total output drops")
        if crc:
            add(f, "CRIT", "L1", "iface-crc",
                f"{name}: {crc} CRC errors — damaged frames on the wire: cable, SFP, or "
                f"duplex mismatch. Re-capture later to confirm it is climbing", f"{name} CRC={crc}")
        if errs and not crc:
            add(f, "WARN", "L1", "iface-input-errors",
                f"{name}: {errs} input errors without CRC — check runts/giants, duplex, "
                f"and the peer's speed setting", f"{name} input errors={errs}")
        if resets:
            add(f, "WARN", "L1", "iface-resets",
                f"{name}: {resets} interface resets — link flapped; correlate with "
                f"`link-downs` on the peer and with power/cable events", f"{name} resets={resets}")
        if late:
            add(f, "WARN", "L1", "iface-late-collisions",
                f"{name}: {late} late collisions — classic duplex mismatch, one side "
                f"full and the other half", f"{name} late={late}")
        if drops:
            add(f, "WARN", "L1", "iface-output-drops",
                f"{name}: {drops} output drops — congestion or a speed mismatch on this "
                f"egress, not a cabling fault", f"{name} drops={drops}")

        dup = re.search(r"^\s*(Full|Half)-duplex,\s*(\d+)Mb/s", chunk, re.M | re.I)
        if dup and dup.group(1).lower() == "half":
            add(f, "WARN", "L1", "iface-half-duplex",
                f"{name}: negotiated half duplex — force matching settings on both sides",
                f"{name} {dup.group(0).strip()}")

        if mgmt_ip and re.search(rf"Internet address is {re.escape(mgmt_ip)}/", chunk):
            add(f, "INFO", "L1", "iface-mgmt",
                f"{name} carries the management IP {mgmt_ip} — never touch this interface "
                f"while diagnosing; you will lose the session", name)

    # ARP / L2-L3 boundary
    arp_rows = re.findall(r"^Internet\s+(\d+\.\d+\.\d+\.\d+)\s+\S+\s+(\S+)\s+(\S+)\s+(\S+)\s*$",
                          text, re.M)
    if arp_rows:
        incomplete = [r for r in arp_rows if r[3].lower() in ("incomplete", "<incomplete>")]
        if incomplete:
            add(f, "WARN", "L2", "arp-incomplete",
                f"{len(incomplete)} ARP entr(y/ies) unresolved — host not answering on this "
                f"segment: wrong VLAN, port isolation, or the host is simply absent",
                ", ".join(r[0] for r in incomplete[:5]))

    # routes
    for m in re.finditer(r"^Gateway of last resort is (.+)$", text, re.M):
        if "not set" in m.group(1):
            add(f, "WARN", "L3", "no-default-route",
                "no gateway of last resort — traffic to unknown destinations is dropped here",
                m.group(0).strip())


# ------------------------------------------------------------------ mikrotik
def parse_mikrotik(text, f, mgmt_ip):
    # /interface print detail
    for m in re.finditer(r"^\s*\d+\s+([DXIRS ]{0,6})\s+name=\"([^\"]+)\"(.*?)(?=\n\s*\d+\s+[DXIRS ]{0,6}\s+name=|\nFlags:|\Z)",
                         text, re.S | re.M):
        flags, name, body = m.group(1), m.group(2), m.group(3)
        downs = re.search(r"link-downs=(\d+)", body)
        lastdown = re.search(r"last-link-down-time=(\S+ \S+)", body)
        mtu = re.search(r"actual-mtu=(\d+)", body)
        if "X" in flags:
            add(f, "WARN", "L1", "iface-disabled",
                f"{name}: disabled by config (`disable`) — enable it before chasing L2",
                f"{name} flags={flags.strip() or '-'}")
            continue
        if "R" not in flags:
            add(f, "CRIT", "L1", "iface-not-running",
                f"{name}: not running — no link. Cable, SFP, or peer port down. "
                f"Nothing above L1 can work", f"{name} flags={flags.strip() or '-'}")
            continue
        if downs and int(downs.group(1)) > 0:
            add(f, "WARN", "L1", "iface-link-flaps",
                f"{name}: link went down {downs.group(1)}x"
                + (f", last at {lastdown.group(1)}" if lastdown else "")
                + " — intermittent: cable, PoE budget, or a flapping peer",
                f"{name} link-downs={downs.group(1)}")
        if mtu and mtu.group(1) != "1500" and not name.startswith("lo"):
            add(f, "INFO", "L1", "iface-mtu",
                f"{name}: actual-mtu={mtu.group(1)} — not 1500; check MTU consistency on "
                f"the path before blaming PMTUD",
                f"{name} mtu={mtu.group(1)}")

    # /ip route print
    for m in re.finditer(r"^\s*\d+\s+([A-Za-z ]{0,6})\s+(\d+\.\d+\.\d+\.\d+/\d+)\s+(\S+)\s+(\d+)",
                         text, re.M):
        flags, dst, gw, dist = m.group(1), m.group(2), m.group(3), m.group(4)
        if "A" not in flags and "C" not in flags and "d" not in flags:
            add(f, "CRIT", "L3", "route-inactive",
                f"route {dst} via {gw} is INACTIVE (no `A` flag) — the gateway is "
                f"unreachable, so this destination is dead even though the route exists",
                f"{dst} gateway={gw} flags={flags.strip()}")

    # dhcp client
    if re.search(r"status=\S*bound", text):
        add(f, "INFO", "L3", "dhcp-bound", "DHCP client has a lease — losing it changes the "
                                         "management IP, so do not bounce that interface")


# ------------------------------------------------------------------ reporting
def emit(f):
    f.sort(key=lambda x: (SEV[x[0]], x[1]))
    counts = {s: sum(1 for x in f if x[0] == s) for s in SEV}
    print(f"  CRIT={counts['CRIT']} WARN={counts['WARN']} INFO={counts['INFO']}")
    cur_layer = None
    for sev, layer, rule, why, ev in f:
        if layer != cur_layer:
            print(f"\n  -- {layer} --")
            cur_layer = layer
        print(f"  [{sev}] {layer} {rule}: {why}")
        if ev:
            print(f"           {ev}")
    return counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--vendor", choices=["cisco", "mikrotik"], default=None)
    ap.add_argument("--mgmt-ip", default=None,
                    help="mark the interface carrying this address as untouchable")
    a = ap.parse_args()

    text = "\n".join(open(p, errors="replace").read() for p in a.files)
    vendor = a.vendor or detect(text)
    print(f"vendor={vendor} files={len(a.files)} mgmt_ip={a.mgmt_ip or '-'}")

    f = findings_new()
    (parse_mikrotik if vendor == "mikrotik" else parse_cisco)(text, f, a.mgmt_ip)
    if not f:
        print("  no finding — either the capture is clean or the command that would "
              "show the fault was not included")
        return 0
    counts = emit(f)

    print("\n  Reminder: error counters are only meaningful as a delta. Re-capture after "
          "traffic and compare, otherwise an old CRC count reads as a live fault.")
    if counts["CRIT"]:
        print("VERDICT: L1/L2 fault present — fix the physical/link cause before any "
              "config change. A config edit cannot repair a down link or bad cable.")
        return 1
    print("VERDICT: no link-layer blocker — continue up the ladder (L2 VLAN/STP, then L3 route).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
