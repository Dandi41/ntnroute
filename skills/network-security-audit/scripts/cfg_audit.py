#!/usr/bin/env python3
"""Audit a saved network config for security hardening findings.

Text output, exit 1 when a CRITICAL hardening finding applies.

Usage:
  cfg_audit.py <config-file> [--mgmt-ip IP] [--vendor cisco|mikrotik]

This tool audits configs only. It never takes part in the change workflow:
changes are governed by the plan approval gate and rollback generation in
the network-change-management skill.

Vendor auto-detect: RouterOS export (`/interface ethernet`, `/ip address`) vs
Cisco-style (`version 15`, `interface Ethernet`).
"""
import argparse
import re
import sys

CRIT, WARN, INFO = "CRIT", "WARN", "INFO"
SEV_ORDER = {CRIT: 0, WARN: 1, INFO: 2}


def detect_vendor(text, forced=None):
    if forced:
        return forced
    if re.search(r"^/interface ethernet|^# .* by RouterOS|^/ip address", text, re.M):
        return "mikrotik"
    return "cisco"


def add(findings, sev, rule, why, evidence=""):
    findings.append((sev, rule, why, evidence.strip()))


# ---------------------------------------------------------------- cisco rules
def audit_cisco(text, mgmt_ip, findings):
    lines = text.splitlines()

    if re.search(r"^username \S+ (password|secret) 0 ", text, re.M):
        ev = [l for l in lines if re.match(r"^username \S+ (password|secret) 0 ", l)]
        add(findings, CRIT, "plaintext-password",
            "credential stored cleartext, and every backup copy inherits it",
            ev[0] if ev else "")
    if re.search(r"^enable (password|secret) 0 ", text, re.M):
        add(findings, CRIT, "plaintext-enable", "enable secret stored cleartext (type 0)")
    if re.search(r"^(enable password|enable secret) ", text, re.M) is None:
        add(findings, WARN, "no-enable-secret", "no enable secret: privileged exec reachable from console")

    for header, body in split_blocks(lines, r"^line (vty|con|aux) "):
        joined = "\n".join(body)
        bare_login = re.search(r"^\s*login\s*$", joined, re.M)
        line_pw = re.search(r"^\s*password ", joined, re.M)
        if header.startswith("line vty"):
            if bare_login and not line_pw:
                add(findings, CRIT, "vty-login-without-password",
                    f"{header}: `login` with no line password = unauthenticated access", header)
            elif not bare_login and not re.search(r"^\s*login", joined, re.M):
                add(findings, WARN, "vty-no-auth", f"{header}: no login method", header)
            if re.search(r"^\s*access-class \d+ in", joined, re.M) is None:
                add(findings, INFO, "vty-no-access-class",
                    f"{header}: management access not restricted by source IP", header)
        m = re.search(r"^\s*transport input (all|telnet)\s*$", joined, re.M)
        if m:
            add(findings, WARN, "vty-cleartext", f"{header}: telnet accepted on a management line", m.group(0).strip())
        m = re.search(r"^\s*exec-timeout 0 0", joined, re.M)
        if m:
            add(findings, WARN, "no-idle-timeout",
                f"{header}: idle session never expires, privilege stays open", f"{header} / exec-timeout 0 0")

    if re.search(r"^ip http server\s*$", text, re.M):
        add(findings, WARN, "http-server-on", "plaintext HTTP management enabled", "ip http server")
    for l in lines:
        if re.match(r"^\s*snmp-server community (public|private)\b", l):
            add(findings, CRIT, "snmp-default-community", "default SNMP community string", l)
        elif re.match(r"^\s*snmp-server community \S+\s*(RO|RW)?\s*$", l):
            add(findings, WARN, "snmp-community-no-acl", "SNMP community readable from any source", l)
    if re.search(r"^service password-encryption", text, re.M) is None:
        add(findings, INFO, "no-password-encryption",
            "`service password-encryption` off: the next line/enable password lands cleartext")
    if re.search(r"^ip domain name\s+\S{1,2}\s*$", text, re.M):
        add(findings, INFO, "placeholder-domain",
            "placeholder `ip domain name`: RSA keygen for SSH will refuse a one-label domain")
    if re.search(r"^banner (login|motd)", text, re.M) is None:
        add(findings, INFO, "no-banner", "no login banner (unauthorized-access notice missing)")
    for l in lines:
        if re.match(r"^ip route 0\.0\.0\.0 ", l):
            add(findings, WARN, "default-route",
                "default route present: any change to it cuts every remote path", l)
    if mgmt_ip:
        iface = interface_of_ip(lines, mgmt_ip)
        if iface:
            add(findings, INFO, "mgmt-interface",
                f"{mgmt_ip} is on `{iface}` — that interface and its address are untouchable",
                f"interface {iface}")
        else:
            add(findings, WARN, "mgmt-ip-not-in-config",
                f"{mgmt_ip} is not a static interface address (DHCP?) — the lease is the only path in")


# ------------------------------------------------------------- mikrotik rules
def audit_mikrotik(text, mgmt_ip, findings):
    lines = text.splitlines()

    if re.search(r"^/ip service", text, re.M) is None:
        add(findings, CRIT, "default-services",
            "no `/ip service` block in export = RouterOS defaults open: telnet 23, ftp 21, www 80, winbox 8291")
    if re.search(r"^/ip firewall filter", text, re.M) is None:
        add(findings, WARN, "no-firewall-filter",
            "no input filter: every service on every interface is reachable")
    if re.search(r"^/ip firewall address-list", text, re.M) and \
       re.search(r"^/ip firewall filter", text, re.M) is None:
        add(findings, WARN, "address-list-unused", "address-list defined but no filter consumes it")

    static = {}
    for l in lines:
        m = re.match(r"^add address=\S+ interface=(\S+)", l)
        if m:
            static.setdefault(m.group(1), set()).add(l)
    for l in section(lines, "/ip dhcp-client"):
        m = re.search(r"interface=(\S+)", l)
        if m and m.group(1) in static:
            add(findings, CRIT, "dhcp-client-on-static",
                f"{m.group(1)} has both a static address and a DHCP client: a new lease can replace the management IP",
                l.strip())
    for l in lines:
        if re.match(r"^add dst-address=0\.0\.0\.0/0 ", l):
            add(findings, WARN, "default-route", "default route present", l.strip())
    if mgmt_ip:
        hit = [l for l in lines if mgmt_ip + "/" in l]
        if hit:
            add(findings, INFO, "mgmt-address",
                f"{mgmt_ip} is configured here — that line is untouchable", hit[0].strip())
        else:
            add(findings, WARN, "mgmt-ip-not-in-config",
                f"{mgmt_ip} is not a static address (DHCP client) — losing the lease locks you out")
    if re.search(r"^/system identity", text, re.M) is None:
        add(findings, INFO, "no-identity", "no `/system identity`: device unidentifiable in backups")


def split_blocks(lines, header_re):
    out, cur, body = [], None, []
    for l in lines:
        if re.match(header_re, l):
            if cur:
                out.append((cur, body))
            cur, body = l.strip(), []
        elif cur is not None:
            if re.match(r"^\S", l) and not l.startswith("!"):
                out.append((cur, body))
                cur, body = None, []
            else:
                body.append(l)
    if cur:
        out.append((cur, body))
    return out


def section(lines, header):
    out, on = [], False
    for l in lines:
        if l.startswith("/"):
            on = (l.strip() == header)
            continue
        if on:
            out.append(l)
    return out


def interface_of_ip(lines, ip):
    cur = None
    for l in lines:
        m = re.match(r"^interface (\S+)", l)
        if m:
            cur = m.group(1)
        elif re.match(rf"^\s*ip address {re.escape(ip)}\b", l):
            return cur
    return None


def emit(findings, out):
    findings.sort(key=lambda f: SEV_ORDER[f[0]])
    counts = {s: sum(1 for f in findings if f[0] == s) for s in (CRIT, WARN, INFO)}
    print(f"  CRIT={counts[CRIT]} WARN={counts[WARN]} INFO={counts[INFO]}", file=out)
    for sev, rule, why, ev in findings:
        print(f"  [{sev}] {rule}: {why}", file=out)
        if ev:
            print(f"         {ev}", file=out)
    return counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--mgmt-ip", default=None)
    ap.add_argument("--vendor", choices=["cisco", "mikrotik"], default=None)
    a = ap.parse_args()

    cfg_text = open(a.config, errors="replace").read()
    vendor = detect_vendor(cfg_text, a.vendor)
    print(f"vendor={vendor} mgmt_ip={a.mgmt_ip or '-'}")

    findings = []
    (audit_mikrotik if vendor == "mikrotik" else audit_cisco)(cfg_text, a.mgmt_ip, findings)
    print("== config findings ==")
    counts = emit(findings, sys.stdout)
    if counts[CRIT]:
        print("VERDICT: HARDENING REQUIRED — fix every CRIT, then re-audit.")
        return 1
    print("VERDICT: no CRIT hardening finding" + ("; WARN items are accepted risks." if counts[WARN] else "."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
