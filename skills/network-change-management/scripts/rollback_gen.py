#!/usr/bin/env python3
"""Derive a rollback script from a change script, following the rules that a
naive `no <line>` prefixer gets wrong.

Usage:
  rollback_gen.py <change-script> [--vendor cisco|mikrotik] [--existing-config F]
                  [--out FILE]

Rules:
  - top-level line        -> `no <line>`
  - line already `no X`   -> `X`            (the undo of a negation)
  - block header + body   -> header once, then `no <child>` per child
  - header with no body   -> `no <header>`  (it was a create)
  - navigation/comments   -> dropped (configure terminal, end, exit, commit, save, !)

--existing-config warns when the rollback would delete a parent object that
exists on the device independently of this change (a real lockout risk).
Exit 1 when the generated rollback looks unsafe, 0 otherwise.
"""
import argparse
import re
import sys

NAV = re.compile(
    r"^(configure( terminal)?|end|exit|return|system-view|quit|"
    r"commit|save|save force|write memory|write|Y|y|yes|no page|"
    r"terminal length 0|screen-length 0 temporary|screen-length disable|"
    r"set cli screen-length 0)$",
    re.I,
)
# A path-only line in a RouterOS-style script is a context switch, not state.
PATH_ONLY = re.compile(r"^/[\w\- ]+$")
SESSIONSCOPE = re.compile(r"^(interface|line|router|policy-map|class-map|"
                          r"ip dhcp pool|ip access-list|route-map)\b", re.I)
# Blocks whose header alone carries state worth undoing.
CREATE_HINT = re.compile(r"^(vlan \d+|ip route \S+|ip dhcp pool \S+|"
                         r"ip access-list \S+|router \w+|route-map \S+|"
                         r"policy-map \S+|class-map \S+)$", re.I)
# `no X` where X is idempotent to re-emit: the interface was already up, the
# feature was already off. Emitting X back would *create* the state, which is
# the opposite of undoing.
NOOP_NO = re.compile(r"^no (shutdown|ip domain lookup|ip http server|"
                     r"ip http secure-server|ipv6 cef|cdp run|service pad|"
                     r"ip source-route|ip bootp server)$", re.I)
# `no X` that removes state. Re-adding X needs the pre-change *value*, which the
# script does not carry — a bare `X` is an incomplete command, not a rollback.
DESTRUCTIVE_NO = re.compile(
    r"^no (ip address|ip route|vlan|username|line |interface |enable |"
    r"switchport|encapsulation|channel-group|ip default-gateway|ntp server|"
    r"logging host|snmp-server|bridge-group|ip nat|access-list|"
    r"ip dhcp pool|crypto|aaa)", re.I)


def negate(line):
    return "no " + line


def unnegate(line):
    return re.sub(r"^no +", "", line)


def negate_child(c):
    """Inverse of one child line inside a block."""
    # `no shutdown` -> `shutdown` and back are true inverses, but a shutdown
    # taking down a live link is exactly the blast-radius case; flag it.
    if re.match(r"^no shutdown$", c, re.I):
        return ["# WARNING rollback shuts the link down: shutdown",
                "shutdown"]
    if re.match(r"^shutdown$", c, re.I):
        return ["no shutdown"]
    if c.startswith("no "):
        # e.g. `no description` -> description needs the old text, not known here
        if re.match(r"^no (shutdown|description|ip address|mtu)$", c, re.I):
            return [f"# TODO restore old value from snapshot: {unnegate(c)}"]
        return [unnegate(c)]
    if re.match(r"^description\b", c, re.I):
        return ["no description"]
    if re.match(r"^ip address\b", c, re.I):
        return ["# TODO restore old address from snapshot: no ip address", "no ip address"]
    return [negate(c)]


def vendor_default(text):
    if re.search(r"^/\S|^add .*=", text, re.M):
        return "mikrotik"
    return "cisco"


def generate(script, vendor, cfg_text=""):
    out, warns = [], []
    lines = [l.rstrip() for l in script.splitlines()]
    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.strip()
        i += 1
        if not line or line.startswith(("#", "!")) or NAV.match(line):
            continue
        if vendor == "mikrotik" and PATH_ONLY.match(line):
            # RouterOS: a context line must be re-emitted with every child, and
            # removal is by `remove [find ...]`, not by `no`.
            children, j = [], i
            while j < len(lines):
                nxt = lines[j].strip()
                if not nxt or nxt.startswith(("#", "!")):
                    j += 1
                    continue
                if PATH_ONLY.match(nxt):
                    break
                children.append(nxt)
                j += 1
            if not children:
                continue
            for c in children:
                if re.match(r"^(add|set)\b", c):
                    warns.append(f"RouterOS `{line}` / `{c}`: rollback is `remove [find ...]` "
                                 f"of the object you add, or the inverse `set` of the old value — "
                                 f"written as a placeholder for manual review")
                    out.append(f"{line} remove [find]  # TODO: narrow the find to the object you added")
                elif re.match(r"^remove\b", c):
                    warns.append(f"RouterOS `{line} / {c}`: removed objects cannot be recreated from "
                                 f"the script alone; restore from the pre-change export")
                    out.append(f"# TODO restore removed object: {line} {c}")
                else:
                    out.append(f"# TODO manual rollback: {line} {c}")
            i = j
            continue

        # collect an indented body (Cisco-style block)
        body = []
        while i < len(lines):
            nxt = lines[i]
            if not nxt.strip() or nxt.startswith("!"):
                i += 1
                continue
            if re.match(r"^\s+\S", nxt):
                body.append(nxt.strip())
                i += 1
                continue
            break

        if body:
            if cfg_text and header_absent(line, cfg_text):
                # whole block is new: undoing it means deleting the parent, not
                # peeling off each child
                out.append(negate(line))
                warns.append(f"`{line}` did not exist before this change, so the rollback "
                             f"deletes it entirely (`{negate(line)}`)")
                continue
            out.append(line)
            for c in body:
                out.extend(negate_child(c))
            continue

        # headerless / childless line
        if line.startswith("no "):
            if NOOP_NO.match(line):
                warns.append(f"`{line}` is idempotent — there is nothing to restore, so it is "
                             f"omitted from the rollback (re-emitting it would remove the state, "
                             f"not add it back)")
                continue
            if DESTRUCTIVE_NO.match(line):
                warns.append(f"`{line}` removes state; the pre-change value is not in the script "
                             f"— take it from the pre-change snapshot, do not guess")
                out.append(f"# TODO restore from snapshot: {line}")
                continue
            out.append(unnegate(line))
        elif CREATE_HINT.match(line):
            out.append(negate(line))
        elif vendor == "mikrotik":
            out.append(f"# TODO manual rollback: {line}")
            warns.append(f"RouterOS line needs a hand-written inverse: {line}")
        else:
            out.append(negate(line))

    return out, warns


def header_absent(header, cfg_text):
    """True when the block header is not present in the pre-change config."""
    h = header.strip()
    return not re.search(rf"^{re.escape(h)}\s*$", cfg_text, re.M)


def check_parent_deletion(rollback, cfg_text):
    """Flag `no <header>` where the header exists in the pre-change config — that
    is a create, not a modification, and `no` on it deletes the whole object."""
    problems = []
    if not cfg_text:
        return problems
    cfg_lines = [l.strip() for l in cfg_text.splitlines()]
    for l in rollback:
        s = l.strip()
        if not s.startswith("no "):
            continue
        target = s[3:].strip()
        if not any(x == target for x in cfg_lines):
            # not present before -> deleting it is exactly the undo
            continue
        problems.append(
            f"`{s}` — `{target}` already existed before this change, so this deletes an "
            f"object you did not create")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("--vendor", choices=["cisco", "mikrotik"], default=None)
    ap.add_argument("--existing-config", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    script = open(a.script, errors="replace").read()
    cfg = open(a.existing_config, errors="replace").read() if a.existing_config else ""
    vendor = a.vendor or vendor_default(cfg or script)

    lines, warns = generate(script, vendor, cfg)
    problems = check_parent_deletion(lines, cfg)
    text = "\n".join(lines) + "\n"

    if a.out:
        open(a.out, "w").write(text)
        print(f"wrote {len(lines)} rollback line(s) -> {a.out}", file=sys.stderr)
    print(f"vendor={vendor} rollback_lines={len(lines)}")
    print("--- rollback script ---")
    print(text, end="")
    if warns:
        print("--- review needed ---")
        for w in warns:
            print(f"  {w}")
    if problems:
        print("--- UNSAFE ---")
        for p in problems:
            print(f"  {p}")
        print("VERDICT: REWRITE — this rollback can delete more than the change added.")
        return 1
    print("VERDICT: rollback candidate — read it line by line before applying.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
