#!/usr/bin/env python3
"""Live security audit, read-only, plus optional CVE research hook.

Usage:
  sec_audit.py <ref> [--mgmt-ip IP] [--cve] [--json]
  sec_audit.py <ref> ... --config <backup-file>

Runs brand-appropriate read-only commands through `ntn exec` (services, users,
SSH, firewall state, OS version), parses the transcripts, and prints findings.
With --config <backup-file> it also reuses cfg_audit.py's config rules on the
saved config. With --cve it stops after printing the detected OS version and
the exact research procedure — CVE lookup happens via web tools in chat, never
guessed by this script.

With --json the script prints one machine-readable JSON object:
  {"hostname","ip","brand","status","os","error","findings":[{"severity","rule",
   "category","why","evidence"}],"counts":{...}}
status is "complete" or "unreachable"; severity uses canonical names
(CRITICAL/HIGH/MEDIUM/LOW/INFO). Exit 1 when a CRITICAL finding exists.
Exit 2 when ntn collection failed (status "unreachable").
"""
import argparse
import re
import subprocess
import sys
import os

CRIT, WARN, INFO = "CRIT", "WARN", "INFO"
SEV = {CRIT: 0, WARN: 1, INFO: 2}
SEV_CANONICAL = {CRIT: "CRITICAL", WARN: "MEDIUM", INFO: "INFO"}
DEVICES = os.path.expanduser("~/.ntnroute/devices.json")


def add(f, sev, rule, why, ev=""):
    f.append((sev, rule, why, ev.strip()))


def resolve_ref(ref):
    import json
    with open(DEVICES) as fh:
        data = json.load(fh)
    items = data if isinstance(data, list) else data.get("devices", [])
    for d in items:
        if str(d["id"]) == str(ref) or d["hostname"].lower() == str(ref).lower() \
           or d["ip"] == str(ref):
            return d
    raise SystemExit(f"device not found: {ref}")


def collect(ref, cmds):
    """Run ntn exec with several commands; return combined transcript."""
    argv = ["ntn", "exec", str(ref)] + list(cmds)
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=300)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"COLLECT FAILED: {e}", file=sys.stderr)
        sys.exit(2)
    return r.stdout + r.stderr


# ------------------------------------------------------------------ mikrotik
def parse_mikrotik(t, findings):
    # services: anchor on the /ip service print table shape
    svc_rows = re.findall(r"^\d+\s+(?:(\w)\s+)?(\S+)\s+(\d+)\s+\S+\s+(\d+)", t, re.M)
    for flag, name, port, _ in svc_rows:
        if name in ("telnet", "ftp", "www", "api"):
            add(findings, CRIT, "service-insecure",
                f"{name} ENABLED — port {port} plaintext, credentials & data travel over "
                f"an unencrypted path; disable unless truly needed",
                f"{name} port={port}")
        elif flag == "X":
            add(findings, INFO, "service-disabled", f"{name} ({port}) disabled — good", f"{name} port={port}")
        elif name == "winbox":
            add(findings, INFO, "service-winbox",
                f"winbox ({port}) enabled — make sure it is restricted by source address or via VPN",
                f"{name} port={port}")
        else:
            add(findings, INFO, "service-encrypted", f"{name} ({port}) enabled (encrypted)", f"{name} port={port}")

    m = re.search(r"^\s+strong-crypto:\s*(\S+)", t, re.M)
    if m and m.group(1) == "no":
        add(findings, WARN, "weak-crypto",
            "strong-crypto: no — SSH/host key uses weak crypto; enable "
            "`/ip ssh set strong-crypto=yes`", m.group(0).strip())
    m = re.search(r"host-key-type:\s*(\S+)", t)
    if m and m.group(1) == "rsa":
        add(findings, INFO, "ssh-rsa-hostkey", "RSA host key — consider ecdsa/ed25519", m.group(0).strip())

    # users: only rows inside the /user print table (anchored by its columns line)
    user_zone = re.search(
        r"Columns: NAME, GROUP, LAST-LOGGED-IN, INACTIVITY-POLICY\n(.*?)(?=\n\s*\n|\nFlags:|\nColumns:|\Z)",
        t, re.S)
    if user_zone:
        for line in user_zone.group(1).splitlines():
            m = re.match(r"^\d+\s+(\w?)\s+(\S+)\s+(\S+)\s+(.*)$", line)
            if not m:
                continue
            flag, name, group, rest = m.groups()
            policy = "none" if "none" in rest else rest.strip()
            if flag == "E":
                add(findings, WARN, "user-expired",
                    f"user `{name}` password EXPIRED — must be changed before the account works", f"user {name}")
            if "none" in rest:
                add(findings, WARN, "user-no-inactivity-policy",
                    f"user `{name}` has no inactivity policy", f"user {name} policy={policy}")
            if group == "full":
                add(findings, INFO, "user-full-group",
                    f"user `{name}` full — narrow it to a smaller group unless needed", f"user {name}")

    m = re.search(r"installed-version:\s*(\S+)", t)
    version = m.group(1) if m else "unknown"
    return {"vendor": "mikrotik", "os": f"RouterOS {version}", "version": version}


# --------------------------------------------------------------------- cisco
def parse_cisco(t, findings):
    m = re.search(r"Cisco IOS Software.*?Version\s+([0-9.()A-Za-z]+)", t)
    version = m.group(1) if m else "unknown"
    if version != "unknown":
        add(findings, INFO, "os-version", f"IOS {version} — recorded for CVE checking", f"Version {version}")
    if re.search(r"DEVELOPMENT TEST SOFTWARE|INTERNAL USE ONLY", t):
        add(findings, WARN, "os-dev-build",
            "DEVELOPMENT/TEST image build — not for production; receives no public security patch releases", version)

    m = re.search(r"HTTP server status:\s*(\S+)", t)
    if m:
        if m.group(1).lower() == "enabled":
            add(findings, CRIT, "http-server-enabled", "ip http server ENABLED — plaintext management; disable", m.group(0).strip())
        else:
            add(findings, INFO, "http-server-disabled", "ip http server disabled — good", m.group(0).strip())
    m = re.search(r"HTTP secure server status:\s*(\S+)", t)
    https_on = bool(m and m.group(1).lower() == "enabled")
    m2 = re.search(r"HTTP secure server ciphersuite:\s*(.+)", t)
    if m2 and ("3des" in m2.group(1) or "des-" in m2.group(1) or "rc4" in m2.group(1)):
        sev = WARN if https_on else INFO
        add(findings, sev, "http-weak-ciphersuite",
            f"weak HTTPS ciphersuite ({'active' if https_on else 'configured but off'}) — "
            f"set `ip http secure-ciphersuite` to AES only", m2.group(1).strip())

    m = re.search(r"SSH version (\d+)", t)
    if m:
        if m.group(1) == "1":
            add(findings, CRIT, "ssh-v1", "SSH v1 still allowed — force `ip ssh version 2`", m.group(0).strip())
        else:
            add(findings, INFO, "ssh-v2", "SSH v2", m.group(0).strip())
    if re.search(r"^(SSH|ssh).*(not enabled|disabled)", t, re.M):
        add(findings, CRIT, "ssh-disabled", "SSH not enabled — plaintext management", "")

    return {"vendor": "cisco", "os": f"Cisco IOS {version}", "version": version}


# ------------------------------------------------------------------- report
CATEGORY = {
    "service": "service exposure", "weak": "crypto", "user": "accounts",
    "ssh": "ssh", "os": "os/version", "perimeter": "perimeter", "acl": "perimeter",
    "http": "management plane",
}


def audit_device(ref, mgmt_ip=None, config=None, cve=False):
    """Audit one device; return a structured result dict."""
    import json
    try:
        dev = resolve_ref(ref)
    except SystemExit as e:
        return {"hostname": str(ref), "ip": "", "brand": "", "status": "unreachable",
                "os": "", "error": str(e), "findings": [], "counts": {}}
    brand = dev.get("brand", "").lower()
    findings = []
    osinfo = {"vendor": brand or "unknown", "os": "unknown", "version": "unknown"}
    status, error = "complete", ""
    if brand.startswith("mikrotik"):
        cmds = ["/system resource print", "/system package update print",
                "/ip service print", "/ip ssh print",
                "/user print", "/ip firewall filter print"]
    elif brand.startswith("cisco"):
        cmds = ["show version", "show ip ssh", "show ip http server status",
                "show users", "show run | section line"]
    else:
        return {"hostname": dev["hostname"], "ip": dev["ip"], "brand": brand,
                "status": "unreachable",
                "os": "", "error": f"brand '{brand}' has no live audit battery yet",
                "findings": [], "counts": {}}

    try:
        r = subprocess.run(["ntn", "exec", str(ref)] + cmds,
                           capture_output=True, text=True, timeout=300)
        text = r.stdout + r.stderr
        failed = (r.returncode != 0) or auth_failed_text(text)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        text, failed = "", True
        error = f"collection failed: {e}"
    if failed:
        detail = error or "ntn exec failed (connection/auth or command error)"
        return {"hostname": dev["hostname"], "ip": dev["ip"], "brand": brand,
                "status": "unreachable", "os": "", "error": detail,
                "findings": [], "counts": {}}

    if brand.startswith("mikrotik"):
        osinfo = parse_mikrotik(text, findings)
        if "chain=input" not in text:
            add(findings, CRIT, "perimeter-no-filter",
                "empty input chain — ALL of the services above are reachable from outside; "
                "this chain is what protects the local network from inbound traffic", "")
    else:
        osinfo = parse_cisco(text, findings)
        if re.search(r"access-list \d+ permit ip any any", text):
            add(findings, WARN, "acl-permit-any",
                "access-list permit ip any any — ACL restricts nothing", "")

    counts = {s: sum(1 for x in findings if x[0] == s) for s in (CRIT, WARN, INFO)}
    result = {
        "hostname": dev["hostname"], "ip": dev["ip"], "brand": brand,
        "status": "complete", "os": osinfo["os"], "error": "",
        "findings": [
            {"severity": SEV_CANONICAL[s],
             "rule": rule,
             "category": CATEGORY.get(rule.split("-")[0], rule.split("-")[0]),
             "why": why, "evidence": ev}
            for s, rule, why, ev in sorted(findings, key=lambda x: SEV[x[0]])
        ],
        "counts": {SEV_CANONICAL[k]: v for k, v in counts.items()},
    }
    if config:
        here = os.path.dirname(os.path.abspath(__file__))
        ca = os.path.join(here, "..", "..", "network-change-management", "scripts", "cfg_audit.py")
        if os.path.exists(ca):
            try:
                rc = subprocess.run(["python3", ca, config, "--mgmt-ip", mgmt_ip or dev["ip"]],
                                    capture_output=True, text=True, timeout=120).returncode
                result["config_audit_exit"] = rc
                if rc == 1:
                    result["counts"]["CRITICAL"] = result["counts"].get("CRITICAL", 0) + 1
                    result["findings"].append(
                        {"severity": "CRITICAL", "rule": "config-audit",
                         "category": "config", "why": "cfg_audit.py reported a CRITICAL rule "
                         f"on {config}; run it for the full detail", "evidence": ""})
            except Exception as e:
                result["config_audit_exit"] = -1
                result["error"] = f"config audit failed: {e}"
    if cve:
        result["cve_research"] = [
            f"web_search('{osinfo['os']} CVE security advisory') → verify on NVD/vendor PSIRT",
            f"web_search('{osinfo['os']} hardcoded password exploit incident')",
            "Check https://nvd.nist.gov/ and the vendor's security advisory page",
        ]
    return result


def auth_failed_text(text):
    return bool(re.search(r"Permission denied|no matching|refused|timed out|No route|Connection closed", text))


def emit(f, dev, osinfo, out):
    f.sort(key=lambda x: SEV[x[0]])
    counts = {s: sum(1 for x in f if x[0] == s) for s in (CRIT, WARN, INFO)}
    print(f"device={dev['hostname']} ip={dev['ip']} vendor={osinfo['vendor']} os={osinfo['os']}")
    print(f"  CRIT={counts[CRIT]} WARN={counts[WARN]} INFO={counts[INFO]}")
    cur = None
    for sev, rule, why, ev in f:
        cat = CATEGORY.get(rule.split("-")[0], rule.split("-")[0])
        if cat != cur:
            print(f"\n  -- {cat} --")
            cur = cat
        print(f"  [{sev}] {rule}: {why}")
        if ev:
            print(f"           {ev}")
    return counts


def cve_hook(osinfo):
    print("\n== CVE / vulnerability research ==")
    print(f"Detected OS: {osinfo['os']}")
    print("Run the research yourself via web_search (never guessed by this script):")
    print(f"  1. web_search('{osinfo['os']} CVE security advisory')  → verify on NVD/vendor PSIRT")
    print(f"  2. web_search('{osinfo['os']} hardcoded password exploit incident')")
    print("  3. Check https://nvd.nist.gov/ and the vendor's security advisory page")
    print("  4. Record CVEs + official links in the report; don't cite forums alone")
    print("See references/threat-research.md for the full procedure.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ref")
    ap.add_argument("--mgmt-ip", default=None)
    ap.add_argument("--cve", action="store_true",
                    help="print the CVE research procedure for the detected OS")
    ap.add_argument("--config", default=None,
                    help="file backup config; reuses cfg_audit.py rules")
    ap.add_argument("--json", action="store_true",
                    help="print one machine-readable JSON result object")
    a = ap.parse_args()

    if a.json:
        import json
        result = audit_device(a.ref, mgmt_ip=a.mgmt_ip, config=a.config, cve=a.cve)
        print(json.dumps(result))
        if result["status"] == "unreachable":
            return 2
        if result["counts"].get("CRITICAL", 0):
            return 1
        return 0

    dev = resolve_ref(a.ref)
    brand = dev.get("brand", "").lower()

    if brand.startswith("mikrotik"):
        cmds = ["/system resource print", "/system package update print",
                "/ip service print", "/ip ssh print",
                "/user print", "/ip firewall filter print"]
        text = collect(a.ref, cmds)
        osinfo = parse_mikrotik(text, f := [])
    elif brand.startswith("cisco"):
        cmds = ["show version", "show ip ssh", "show ip http server status",
                "show users", "show run | section line"]
        text = collect(a.ref, cmds)
        osinfo = parse_cisco(text, f := [])
    else:
        print(f"brand '{brand}' has no live audit battery yet — use the config audit only "
              f"(see cfg_audit.py) or write a new parser", file=sys.stderr)
        sys.exit(2)

    # firewall/perimeter check, brand-specific
    if brand.startswith("mikrotik"):
        if "chain=input" not in text:
            add(f, CRIT, "perimeter-no-filter",
                "empty input chain — ALL of the services above are reachable from outside; "
                "this chain is what protects the local network from inbound traffic", "")
    elif brand.startswith("cisco"):
        if re.search(r"access-list \d+ permit ip any any", text):
            add(f, WARN, "acl-permit-any", "access-list permit ip any any — ACL restricts nothing", "")

    counts = emit(f, dev, osinfo, sys.stdout)

    config_crit = False
    if a.config:
        here = os.path.dirname(os.path.abspath(__file__))
        # scripts/ -> skill dir -> networking/ -> sibling skill
        ca = os.path.join(here, "..", "..", "network-change-management", "scripts", "cfg_audit.py")
        if os.path.exists(ca):
            print("\n== config findings (from cfg_audit.py) ==")
            rc = subprocess.call(["python3", ca, a.config,
                                  "--mgmt-ip", a.mgmt_ip or dev["ip"]])
            if rc not in (0, 1):
                print("config audit failed", file=sys.stderr)
            config_crit = (rc == 1)

    if a.json:
        import json
        print(json.dumps(osinfo))

    if a.cve:
        cve_hook(osinfo)

    if counts[CRIT] or config_crit:
        src = "live" if counts[CRIT] else "config"
        print(f"\nVERDICT: AUDIT FAIL (CRIT from {src}) — propose hardening via "
              "network-change-management (plan approval gate), don't apply it directly.")
        return 1
    print("\nVERDICT: no CRITICAL — WARN/INFO go onto the ongoing hardening list.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
