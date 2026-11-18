"""No vendor mutation adapter is enabled in this release.

Trust boundaries: inventory/settings/operator filesystem are trusted; device pages,
provider responses and MCP arguments are untrusted. External executables are an
explicit credential-handling trust delegation, not sandboxed plugins.
"""
import hashlib
import json
import os
import re
import secrets
import stat
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit


class Error(Exception):
    pass


def load(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def contains_credentials(value, credentials):
    """Check decoded JSON strings (including keys), not escaped serialization."""
    secrets = tuple(s for s in credentials if isinstance(s, str) and s)

    def contains(item):
        if isinstance(item, str):
            return any(secret in item for secret in secrets)
        if isinstance(item, dict):
            return any(contains(k) or contains(v) for k, v in item.items())
        if isinstance(item, (list, tuple)):
            return any(contains(v) for v in item)
        return False

    return contains(value)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def origin(value):
    if not isinstance(value, str) or not value or any(ord(c) <= 32 or ord(c) == 127 for c in value) or "\\" in value:
        raise Error("origin required without whitespace or backslashes")
    p = urlsplit(value)
    if p.scheme not in ("https", "http") or not p.hostname or p.username or p.password or p.path not in ("", "/") or p.query or p.fragment:
        raise Error("expected exact HTTP(S) origin without credentials/path")
    try:
        port = p.port
    except ValueError:
        raise Error("invalid port") from None
    host = p.hostname.lower()
    if ":" in host:
        host = "[" + host + "]"
    return f"{p.scheme}://{host}" + (f":{port}" if port and port != (443 if p.scheme == "https" else 80) else "")


ACTIONS = {
    "onu.provision": {"onu_id", "serial", "service_vlan"},
    "wan.configure": {"interface", "mode", "vlan"},
    "vlan.configure": {"vlan", "ports", "tagged"},
}


def reviewed_path(value):
    if not isinstance(value, str) or not re.fullmatch(r"/[A-Za-z0-9_./#-]*", value) or value.startswith("//") or ".." in value or value.count("#") > 1:
        raise Error("invalid reviewed path")
    return value


def validate_requests(entries, methods):
    if not isinstance(entries, list) or len(entries) > 64:
        raise Error("invalid reviewed requests")
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"path", "query", "method", "max_requests"}:
            raise Error("invalid reviewed request shape")
        reviewed_path(entry["path"])
        if "#" in entry["path"]:
            raise Error("request paths cannot contain fragments")
        query = entry["query"]
        if (not isinstance(query, str) or len(query) > 1024
                or not re.fullmatch(r"(?:[A-Za-z0-9_.~!$&'()*+,;=:@/?-]|%[0-9A-Fa-f]{2})*", query)):
            raise Error("invalid exact request query")
        if entry["method"] not in methods or type(entry["max_requests"]) is not int or not 1 <= entry["max_requests"] <= 16:
            raise Error("invalid reviewed request method or count")
        key = (entry["path"], query, entry["method"])
        if key in seen:
            raise Error("duplicate reviewed request")
        seen.add(key)


def require_auth_requests(profile):
    auth = profile.get("authentication")
    if auth is not None and not auth["requests"]:
        raise Error("reviewed authentication requests required; endpoints unverified")


def validate_profile(p):
    required = {"id", "status", "vendor", "firmware", "read_path", "read_only_reviewed", "fields", "identity", "capabilities", "asset_requests"}
    if not isinstance(p, dict) or not required <= set(p) or set(p) - required - {"authentication", "review_scope"}:
        raise Error("invalid profile shape")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", p["id"]):
        raise Error("invalid profile id")
    if p["status"] not in ("candidate", "reviewed") or type(p["read_only_reviewed"]) is not bool:
        raise Error("invalid profile status")
    for key in ("vendor", "firmware"):
        if not isinstance(p[key], str) or not 1 <= len(p[key]) <= 200:
            raise Error("invalid profile metadata")
    reviewed_path(p["read_path"])
    validate_requests(p["asset_requests"], ("GET",))
    scope = p.get("review_scope", "status")
    if scope not in ("status", "authentication-only"):
        raise Error("invalid review scope")
    auth = p.get("authentication")
    if auth is not None:
        if not isinstance(auth, dict) or set(auth) != {"login_path", "username_selector", "password_selector", "submit_selector", "success_path", "success_selector", "success_text", "requests"}:
            raise Error("invalid authentication profile")
        validate_requests(auth["requests"], ("GET", "POST"))
        for key in ("login_path", "success_path"):
            reviewed_path(auth[key])
        for key in ("username_selector", "password_selector", "submit_selector", "success_selector", "success_text"):
            if not isinstance(auth[key], str) or not 1 <= len(auth[key]) <= 200:
                raise Error("explicit authentication selectors and exact success text required")
    if scope == "authentication-only" and (auth is None or p["read_path"] != auth["success_path"] or p["fields"] != {"status": auth["success_selector"]} or p["identity"] != {"status": auth["success_text"]}):
        raise Error("authentication-only profiles may read only the success marker")
    fields = p["fields"]
    if not isinstance(fields, dict) or not 1 <= len(fields) <= 32:
        raise Error("invalid fields")
    for name, selector in fields.items():
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,40}", name) or re.search(r"pass|secret|token|cookie|key|credential", name, re.I):
            raise Error("secret-like or invalid field")
        if not isinstance(selector, str) or not 1 <= len(selector) <= 200:
            raise Error("invalid selector")
    identity = p["identity"]
    if not isinstance(identity, dict) or not identity or not set(identity) <= set(fields) or any(not isinstance(v, str) or not v for v in identity.values()):
        raise Error("explicit identity field equality required")
    if p["capabilities"] != {a: "unsupported" for a in ACTIONS}:
        raise Error("no write adapter is implemented; capabilities must be unsupported")
    return p


class Core:
    def __init__(self, inventory, profiles, state, provider="skip", executable=None, allow_http_credentials=False):
        self.inventory = Path(inventory)
        self.profiles = Path(profiles).resolve()
        self.state = Path(state)
        self.provider = provider
        self.executable = executable
        self.allow_http_credentials = allow_http_credentials

    def profile(self, name):
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", name):
            raise Error("profile must be an id, not a path")
        path = self.profiles / (name + ".json")
        if path.is_symlink() or path.resolve().parent != self.profiles:
            raise Error("profile path escapes root")
        p = validate_profile(load(path))
        if p["id"] != name:
            raise Error("profile id mismatch")
        return p

    def device(self, ref):
        inventory = load(self.inventory)
        if not isinstance(inventory, dict) or set(inventory) != {"next_id", "devices", "checkpoints", "audit"} or not all(isinstance(inventory[k], list) for k in ("devices", "checkpoints", "audit")) or type(inventory["next_id"]) is not int:
            raise Error("canonical inventory required")
        matches = [d for d in inventory["devices"] if isinstance(d, dict) and str(ref) in (str(d.get("id")), d.get("hostname"), d.get("ip"))]
        if len(matches) != 1:
            raise Error("device missing or ambiguous")
        d = matches[0]
        w = d.get("web")
        if not isinstance(w, dict) or "origin" not in w:
            raise Error("explicit device.web.origin required; SSH address is not a web authorization")
        return d, w, origin(w["origin"])

    def inspect(self, device, profile, *, learn=False):
        p = self.profile(profile)
        if p["status"] != "reviewed" or p["read_only_reviewed"] is not True:
            raise Error("candidate profile cannot connect; review read path/fields/identity first")
        require_auth_requests(p)
        d, w, target = self.device(device)
        if w.get("profile") != profile:
            raise Error("inventory profile binding mismatch")
        credentials = {"username": w.get("username", d.get("username", d.get("user", ""))), "password": w.get("password", d.get("password", d.get("pass", "")))}
        if any(not isinstance(v, str) for v in credentials.values()):
            raise Error("invalid credential type")
        if target.startswith("http:") and any(credentials.values()) and not self.allow_http_credentials:
            raise Error("HTTP credential transport not authorized")
        tls_verify = w.get("tls_verify", True)
        if type(tls_verify) is not bool:
            raise Error("device.web.tls_verify must be an explicit boolean")
        if learn and self.provider not in ("bundled", "playwright"):
            raise Error("DOM learning requires the bundled Playwright provider")
        request = {"protocol": "ntn-web-provider/1", "method": "learn" if learn else "read", "origin": target, "credentials": credentials, "profile": p, "policy": {"same_origin_only": True, "read_only": True, "tls_verify": tls_verify, "timeout_seconds": 20}}
        try:
            if self.provider == "external":
                exe = Path(self.executable or "")
                if not exe.is_absolute() or not exe.is_file() or not os.access(exe, os.X_OK):
                    raise Error("explicit absolute provider executable required")
                # No shell, command arguments, automatic retry, or provider stderr relay.
                result = subprocess.run([str(exe)], input=canonical(request), text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=25, check=False)
                if result.returncode or len(result.stdout) > 65536:
                    raise Error("provider failed")
                response = json.loads(result.stdout)
            elif self.provider in ("bundled", "playwright"):
                from .provider import read
                response = read(request)
            else:
                raise Error("browser provider disabled")
        except Error:
            raise
        except Exception:
            raise Error("provider failed; no retry performed") from None
        expected = {"origin", "values", "controls"} if learn else {"origin", "values"}
        if not isinstance(response, dict) or set(response) != expected or response["origin"] != target:
            raise Error("provider origin/response mismatch")
        values = response["values"]
        if not isinstance(values, dict) or set(values) != set(p["fields"]) or any(not isinstance(v, str) or len(v) > 2048 for v in values.values()):
            raise Error("invalid provider fields")
        # Defense in depth against accidental literal credential echo.
        if contains_credentials(response, credentials.values()):
            raise Error("provider returned credential material")
        if any(values[k] != v for k, v in p["identity"].items()):
            raise Error("device identity mismatch; login screens are not snapshots")
        result = {"device_id": d["id"], "origin": target, "profile": profile, "profile_digest": digest(p), "values": values, "snapshot_kind": "authentication-only" if p.get("review_scope") == "authentication-only" else "partial-operational-not-backup"}
        if learn:
            controls = response["controls"]
            if not isinstance(controls, list) or len(controls) > 64 or len(canonical(controls)) > 16384:
                raise Error("invalid control metadata")
            result["controls"] = controls
        return result

    def private_state(self):
        if self.state.is_symlink():
            raise Error("state directory cannot be symlink")
        self.state.mkdir(mode=0o700, parents=True, exist_ok=True)
        st = self.state.stat()
        if st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) & 0o077:
            raise Error("state directory must be operator-owned mode 0700")

    def save_new(self, name, value):
        self.private_state()
        fd = os.open(self.state / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(canonical(value) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def plan(self, device, profile, action, params, recovery):
        if action not in ACTIONS or not isinstance(params, dict) or set(params) - ACTIONS[action] or not params:
            raise Error("unsupported action or parameter names")
        if any(not isinstance(v, (str, int, bool, list)) for v in params.values()) or len(canonical(params)) > 2048:
            raise Error("invalid parameters")
        if not isinstance(recovery, str) or not 1 <= len(recovery) <= 2048:
            raise Error("concrete operator recovery instructions required")
        d, w, _ = self.device(device)
        private_values = [w.get("username", d.get("username", d.get("user", ""))), w.get("password", d.get("password", d.get("pass", "")))]
        if contains_credentials({"params": params, "recovery": recovery}, private_values):
            raise Error("plan contains credential material")
        for key, value in params.items():
            if key in ("vlan", "service_vlan") and (type(value) is not int or not 1 <= value <= 4094):
                raise Error("VLAN must be an integer from 1 to 4094")
            if isinstance(value, list) and (len(value) > 64 or any(not isinstance(item, str) or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,64}", item) for item in value)):
                raise Error("invalid port list")
            if isinstance(value, str) and not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,128}", value):
                raise Error("invalid parameter value")
        if self.profile(profile).get("review_scope") == "authentication-only":
            raise Error("authentication-only profile cannot provide a configuration baseline")
        baseline = self.inspect(device, profile)
        body = {"version": 1, "nonce": secrets.token_hex(16), "created": int(time.time()), "expires": int(time.time()) + 900, "baseline": baseline, "action": action, "params": params, "recovery": recovery, "verification": "exact reviewed field readback required; adapter not implemented", "executable": False}
        plan_id = digest(body)
        self.save_new(plan_id + ".plan.json", body)
        return {"plan_id": plan_id, "plan": body, "status": "review-only-unsupported-write"}

    def review(self, plan_id):
        if not isinstance(plan_id, str) or not re.fullmatch(r"[a-f0-9]{64}", plan_id):
            raise Error("invalid plan id")
        self.private_state()
        path = self.state / (plan_id + ".plan.json")
        if path.is_symlink():
            raise Error("invalid plan file")
        body = load(path)
        if digest(body) != plan_id:
            raise Error("plan integrity mismatch")
        if body["expires"] <= time.time():
            raise Error("plan expired")
        return body

    def approve(self, plan_id):
        self.review(plan_id)
        self.save_new(plan_id + ".approval.json", {"plan_id": plan_id, "operator_uid": os.getuid(), "approved": int(time.time())})
        return {"plan_id": plan_id, "approved": True, "executable": False}

    def apply(self, plan_id):
        self.review(plan_id)
        # Fail before any provider call: neither approval nor params can enable writes.
        raise Error("unsupported write: no tested vendor mutation/verification/recovery adapter; nothing submitted")

    def dispatch(self, method, args):
        if method == "profiles":
            return [{"id": p["id"], "status": p["status"], "vendor": p["vendor"], "capabilities": p["capabilities"]} for p in (self.profile(f.stem) for f in sorted(self.profiles.glob("*.json")))]
        if method == "capabilities":
            return {a: {"parameters": sorted(fields), "supported": False} for a, fields in ACTIONS.items()}
        if method == "inspect":
            return self.inspect(**args)
        if method == "plan":
            return self.plan(**args)
        if method == "review":
            return self.review(**args)
        if method in ("apply", "rollback"):
            return self.apply(**args)
        raise Error("unknown or forbidden method")
