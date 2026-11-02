#!/usr/bin/env python3
"""Persistent PTY session against a network device CLI (Cisco IOS shape).

    python3 ios_session.py --host 10.0.0.1 --user admin --password 'pw' \
        [--secret ENABLE] --cmd 'show version' --cmd 'show ip interface brief'
    python3 ios_session.py ... --show-config        # full running-config

Reads until the channel goes idle rather than sleeping a fixed time, handles
paging prompts, strips ANSI, and reports the prompt it actually saw so an
enable failure is visible instead of silent.

Uses the installed paramiko. If it raises `IncompatiblePeer: no acceptable kex
algorithm` against old gear, vendor a paramiko that still ships
`diffie-hellman-group14-sha1` and prepend it to sys.path.
"""

import argparse
import re
import socket
import sys
import time

import paramiko

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07")


def clean(raw, echo=None):
    txt = ANSI_RE.sub("", raw).replace("\r\n", "\n").replace("\r", "\n")
    txt = re.sub(r"\x08+", "", txt)
    lines = txt.split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    if echo and lines and echo.strip() and echo.strip() in lines[0]:
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if lines and len(lines[-1]) < 160 and re.search(r"[>#\]\$]\s*$", lines[-1]):
        lines.pop()
    return "\n".join(lines).strip("\n")


def tail_prompt(text):
    plain = ANSI_RE.sub("", text).replace("\r", "")
    m = re.search(r"\n?([^\n]{0,120}?[>#]\s*)$", plain)
    return m.group(1).strip() if m else ""


class Session:
    def __init__(self, host, port, user, password, secret=None):
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client.connect(
            hostname=host, port=port, username=user, password=password,
            timeout=20, banner_timeout=25, auth_timeout=25,
            look_for_keys=False, allow_agent=False,
            disabled_algorithms={"pubkeys": ["rsa-sha2-256", "rsa-sha2-512"]},
        )
        self.chan = self.client.invoke_shell(width=400, height=2000)
        self.chan.settimeout(0.5)
        self.secret = secret or ""
        self.prompt = tail_prompt(self._read(idle=1.5, maxwait=20))

    def _read(self, idle=0.7, maxwait=180):
        buf, start, last = "", time.time(), time.time()
        while time.time() - start < maxwait:
            try:
                data = self.chan.recv(65535)
            except socket.timeout:
                if time.time() - last >= idle:
                    break
                continue
            except Exception:
                break
            if not data:
                break
            buf += data.decode("utf-8", "replace")
            last = time.time()
            if re.search(r"--+\s*More\s*--+|<-+\s*More\s*-+>", ANSI_RE.sub("", buf[-400:])):
                self.chan.send(" ")
                buf += self._read(idle=0.4, maxwait=20)
        return buf

    def send(self, cmd, idle=0.8, maxwait=120):
        self.chan.send(cmd + "\n")
        res = clean(self._read(idle=idle, maxwait=maxwait), echo=cmd)
        self.prompt = tail_prompt(self._read(idle=0.4, maxwait=10)) or self.prompt
        return res

    def enable(self):
        if self.prompt.endswith("#"):
            return "already privileged"
        if not self.secret:
            return "no secret given; staying in user exec"
        self.chan.send("enable\n")
        time.sleep(1.0)
        banner = self._read(idle=0.8, maxwait=10)
        if "assword" not in banner.lower():
            return f"enable did not prompt for a password (prompt {self.prompt!r})"
        self.chan.send(self.secret + "\n")
        time.sleep(1.2)
        self.prompt = tail_prompt(banner + self._read(idle=0.9, maxwait=12)) or self.prompt
        return "privileged OK" if self.prompt.endswith("#") else f"enable FAILED (prompt {self.prompt!r})"

    def close(self):
        for obj in (self.chan, self.client):
            try:
                obj.close()
            except Exception:
                pass


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", required=True)
    p.add_argument("--port", type=int, default=22)
    p.add_argument("--user", required=True)
    p.add_argument("--password", required=True)
    p.add_argument("--secret", default="")
    p.add_argument("--cmd", action="append", default=[])
    p.add_argument("--show-config", action="store_true")
    p.add_argument("--paging", default="terminal length 0")
    a = p.parse_args()

    try:
        s = Session(a.host, a.port, a.user, a.password, a.secret)
    except Exception as exc:
        print(f"connect failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    try:
        print(f"# {s.enable()}")
        if a.paging:
            s.send(a.paging)
        for cmd in a.cmd:
            print(f"\n$ {cmd}")
            print(s.send(cmd))
        if a.show_config:
            print("\n$ show running-config")
            print(s.send("show running-config", idle=1.2, maxwait=300))
        print(f"\n# final prompt: {s.prompt!r}")
    finally:
        s.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
