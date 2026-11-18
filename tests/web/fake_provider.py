#!/usr/bin/env python3
"""Local fixture only. No network access; log call count without credentials."""
import json
import os
import sys
from pathlib import Path
request = json.load(sys.stdin)
if os.environ.get("NTN_TEST_CALLS"):
    with open(os.environ["NTN_TEST_CALLS"], "a") as stream:
        stream.write("read\n")
mode = os.environ.get("NTN_TEST_MODE", "ok")
if mode == "failure":
    print(request["credentials"]["password"], file=sys.stderr)
    sys.exit(2)
values = {"model": "fixture-router", "vlan": "10"}
if mode == "echo":
    values["vlan"] = request["credentials"]["password"]
if mode == "login":
    values["model"] = "Login"
if mode == "extra":
    values["password"] = "untrusted"
print(json.dumps({"origin": "https://evil.invalid" if mode == "redirect" else request["origin"], "values": values}))
