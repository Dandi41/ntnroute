import contextlib
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from web.core import Core, Error, ACTIONS, canonical, digest, origin, validate_profile
from web.__main__ import configured, main, parser
from web.mcp import serve

ROOT = Path(__file__).resolve().parents[2]
FAKE = Path(__file__).with_name("fake_provider.py")


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.profiles = self.root / "profiles"
        self.profiles.mkdir()
        self.p = {"id": "fixture", "status": "reviewed", "vendor": "LOCAL FIXTURE ONLY", "firmware": "fixture-1", "read_path": "/status", "asset_requests": [], "read_only_reviewed": True, "fields": {"model": "#model", "vlan": "#vlan"}, "identity": {"model": "fixture-router"}, "capabilities": {a: "unsupported" for a in ACTIONS}}
        self.write_profile()
        self.inventory = self.root / "devices.json"
        self.inv = {"next_id": 2, "devices": [{"id": 1, "hostname": "lab", "ip": "192.0.2.1", "username": "fixture-user", "password": "fixture-password-unique", "web": {"origin": "https://lab.invalid", "profile": "fixture"}}], "checkpoints": [], "audit": []}
        self.inventory.write_text(json.dumps(self.inv))
        self.original = self.inventory.read_bytes()
        FAKE.chmod(0o700)
        self.core = Core(self.inventory, self.profiles, self.root / "state", "external", str(FAKE))
        self.calls = self.root / "calls"
        env = patch.dict(os.environ, {"NTN_TEST_CALLS": str(self.calls), "NTN_TEST_MODE": "ok"})
        env.start()
        self.addCleanup(env.stop)

    def tearDown(self):
        self.assertEqual(self.inventory.read_bytes(), self.original)

    def write_profile(self):
        (self.profiles / "fixture.json").write_text(json.dumps(self.p))

    def make_plan(self):
        return self.core.plan("lab", "fixture", "vlan.configure", {"vlan": 20}, "Use local serial console and restore saved lab configuration")

    def test_read_snapshot(self):
        result = self.core.inspect("lab", "fixture")
        self.assertEqual(result["values"]["vlan"], "10")
        self.assertEqual(result["snapshot_kind"], "partial-operational-not-backup")
        self.assertNotIn("fixture-password", canonical(result))
        self.assertEqual(self.calls.read_text(), "read\n")

    def test_inventory_ids_and_ip(self):
        for ref in ("1", "lab", "192.0.2.1"):
            self.assertEqual(self.core.device(ref)[0]["id"], 1)

    def test_candidate_never_connects(self):
        self.p["status"] = "candidate"
        self.write_profile()
        with self.assertRaises(Error):
            self.core.inspect("lab", "fixture")
        self.assertFalse(self.calls.exists())

    def test_unreviewed_read_never_connects(self):
        self.p["read_only_reviewed"] = False
        self.write_profile()
        with self.assertRaises(Error):
            self.core.inspect("lab", "fixture")
        self.assertFalse(self.calls.exists())

    def test_profile_paths(self):
        for name in ("../fixture", "/tmp/fixture", "fixture.json", "a/b", "", "a\\b"):
            with self.subTest(name=name), self.assertRaises(Error):
                self.core.profile(name)
        (self.profiles / "escape.json").symlink_to(self.profiles / "fixture.json")
        with self.assertRaises(Error):
            self.core.profile("escape")

    def test_request_declarations_are_strict_and_bounded(self):
        entry = {"path": "/app.js", "query": "v=1", "method": "GET", "max_requests": 1}
        for change in ({"path": "//evil"}, {"path": "/reset#x"}, {"path": "/a?x=1"},
                       {"query": "x=#bad"}, {"query": "x=\n"}, {"query": "%zz"},
                       {"method": "POST"}, {"method": "get"}, {"max_requests": True},
                       {"max_requests": 0}, {"max_requests": 17}, {"extra": True}):
            with self.subTest(change=change), self.assertRaises(Error):
                validate_profile(dict(self.p, asset_requests=[dict(entry, **change)]))
        for entries in (None, {}, [entry, entry], [entry] * 65):
            with self.subTest(entries=entries), self.assertRaises(Error):
                validate_profile(dict(self.p, asset_requests=entries))
        validate_profile(dict(self.p, asset_requests=[entry]))
        missing = dict(self.p)
        del missing["asset_requests"]
        with self.assertRaises(Error):
            validate_profile(missing)

    def test_empty_authentication_requests_never_invoke_any_provider(self):
        p = json.loads((ROOT / "web/profiles/webfig-auth.json").read_text())
        with patch.object(self.core, "profile", return_value=p), self.assertRaisesRegex(Error, "authentication requests"):
            self.core.inspect("lab", "fixture")
        self.assertFalse(self.calls.exists())

    def test_decoded_credential_detector_covers_nested_keys_and_values(self):
        from web.core import contains_credentials
        for secret in ('quote"secret', 'back\\secret', 'unicodé秘密', 'control\n\t\x01secret'):
            for value in ({"x": [{"y": "prefix " + secret}]}, {"x": [{secret: False}]}):
                self.assertTrue(contains_credentials(json.loads(canonical(value)), ["", secret]))
            self.assertFalse(contains_credentials({"safe": [1, None, True, "text"]}, ["", secret]))

    def test_profile_json_schema_matches_shipped_and_fixture_profiles(self):
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest("optional jsonschema unavailable")
        schema = json.loads((ROOT / "web/profile.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        for profile in [self.p] + [json.loads(p.read_text()) for p in (ROOT / "web/profiles").glob("*.json")]:
            validator.validate(profile)
        entry = {"path": "/app.js", "query": "v=1", "method": "GET", "max_requests": 1}
        validator.validate(dict(self.p, asset_requests=[entry]))
        for change in ({"path": "//evil"}, {"query": "#bad"}, {"method": "POST"}, {"max_requests": True}, {"max_requests": 0}):
            self.assertFalse(validator.is_valid(dict(self.p, asset_requests=[dict(entry, **change)])))

    def test_profile_rejects_write_claim(self):
        self.p["capabilities"]["vlan.configure"] = "supported"
        with self.assertRaises(Error):
            validate_profile(self.p)

    def test_profile_rejects_secret_fields_and_paths(self):
        for name in ("password", "api_token", "secret", "cookie"):
            p = json.loads(json.dumps(self.p))
            p["fields"][name] = "#x"
            with self.assertRaises(Error):
                validate_profile(p)
        for path in ("//evil.invalid", "/../admin", "/reset?yes=1", "https://evil.invalid"):
            p = dict(self.p, read_path=path)
            with self.assertRaises(Error):
                validate_profile(p)

    def test_provider_rejects_origin_echo_login_and_extra(self):
        for mode in ("redirect", "echo", "login", "extra", "failure"):
            with self.subTest(mode=mode), patch.dict(os.environ, {"NTN_TEST_MODE": mode}), self.assertRaises(Error) as exc:
                self.core.inspect("lab", "fixture")
            self.assertNotIn("fixture-password", str(exc.exception))
        self.assertEqual(len(self.calls.read_text().splitlines()), 5)

    def test_escaped_credentials_are_rejected_in_provider_and_plan(self):
        for secret in ('quote"secret', 'back\\secret', 'unicodé秘密', 'control\n\t\x01secret'):
            d = dict(self.inv["devices"][0], password=secret)
            with self.subTest(secret=repr(secret)), patch.object(self.core, "device", return_value=(d, d["web"], "https://lab.invalid")):
                with patch.dict(os.environ, {"NTN_TEST_MODE": "echo"}), self.assertRaisesRegex(Error, "credential material"):
                    self.core.inspect("lab", "fixture")
                with self.assertRaisesRegex(Error, "credential material"):
                    self.core.plan("lab", "fixture", "vlan.configure", {"vlan": 20}, "recover " + secret)
                with self.assertRaisesRegex(Error, "credential material"):
                    self.core.plan("lab", "fixture", "vlan.configure", {"ports": [secret]}, "console")
        self.assertFalse(self.core.state.exists())

    def test_timeout_is_not_retried(self):
        with patch("web.core.subprocess.run", side_effect=subprocess.TimeoutExpired("redacted", 25)) as run:
            with self.assertRaises(Error):
                self.core.inspect("lab", "fixture")
        self.assertEqual(run.call_count, 1)

    def test_external_is_single_executable_no_shell(self):
        self.core.executable = str(FAKE) + " --arbitrary"
        with self.assertRaises(Error):
            self.core.inspect("lab", "fixture")
        self.assertFalse(self.calls.exists())

    def test_no_http_credentials(self):
        with patch.object(self.core, "device", return_value=(self.inv["devices"][0], {"profile": "fixture"}, "http://lab.invalid")):
            with self.assertRaises(Error):
                self.core.inspect("lab", "fixture")
        self.assertFalse(self.calls.exists())

    def test_plan_immutable_and_private(self):
        result = self.make_plan()
        ident = result["plan_id"]
        self.assertEqual(digest(result["plan"]), ident)
        self.assertFalse(result["plan"]["executable"])
        path = self.core.state / (ident + ".plan.json")
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.core.state.stat().st_mode), 0o700)
        with self.assertRaises(FileExistsError):
            self.core.save_new(ident + ".plan.json", {})
        body = json.loads(path.read_text())
        body["params"]["vlan"] = 30
        path.write_text(json.dumps(body))
        with self.assertRaises(Error):
            self.core.review(ident)

    def test_plan_expiry(self):
        result = self.make_plan()
        with patch("web.core.time.time", return_value=result["plan"]["expires"] + 1):
            with self.assertRaises(Error):
                self.core.review(result["plan_id"])

    def test_no_writes_even_after_operator_approval(self):
        result = self.make_plan()
        self.core.approve(result["plan_id"])
        for _ in range(2):
            with self.assertRaisesRegex(Error, "nothing submitted"):
                self.core.apply(result["plan_id"])
        self.assertEqual(self.calls.read_text(), "read\n")
        with self.assertRaises(FileExistsError):
            self.core.approve(result["plan_id"])

    def test_state_permissions_and_symlink(self):
        self.core.state.mkdir(mode=0o755)
        with self.assertRaises(Error):
            self.core.private_state()
        self.core.state.rmdir()
        self.core.state.symlink_to(self.profiles, target_is_directory=True)
        with self.assertRaises(Error):
            self.core.private_state()

    def test_unknown_action_secret_params(self):
        for action, params in (("reboot", {}), ("wan.configure", {"password": "secret"})):
            with self.assertRaises(Error):
                self.core.plan("lab", "fixture", action, params, "console")
        self.assertFalse(self.calls.exists())

    def test_mcp_has_no_approval_and_cannot_inject_it(self):
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "approve", "arguments": {"plan_id": "0" * 64}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "apply", "arguments": {"plan_id": "0" * 64, "approved": True}}},
            {"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "inspect", "arguments": {"device": "lab", "profile": "fixture"}}},
        ]
        out = io.StringIO()
        serve(self.core, io.StringIO("\n".join(map(json.dumps, requests))), out)
        responses = list(map(json.loads, out.getvalue().splitlines()))
        self.assertEqual(len(responses), 4)
        self.assertNotIn("approve", [t["name"] for t in responses[1]["result"]["tools"]])
        self.assertIn("error", responses[2])
        self.assertIn("error", responses[3])
        self.assertFalse(self.calls.exists())

    def test_mcp_inspect_contract(self):
        messages = [{"jsonrpc": "2.0", "id": 1, "method": "initialize"}, {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "inspect", "arguments": {"device": "lab", "profile": "fixture"}}}]
        out = io.StringIO()
        serve(self.core, io.StringIO("\n".join(map(json.dumps, messages))), out)
        response = json.loads(out.getvalue().splitlines()[-1])
        self.assertFalse(response["result"]["isError"])
        self.assertEqual(json.loads(response["result"]["content"][0]["text"])["device_id"], 1)

    def test_cli_defaults_installer_settings(self):
        settings = {"version": 1, "browser": {"provider": "existing", "executable": str(FAKE)}, "profiles_dir": str(self.profiles), "state_dir": str(self.root / "private"), "browsers_path": str(self.root / "browsers")}
        (self.root / "web-settings.json").write_text(json.dumps(settings))
        with patch.dict(os.environ, {"NTN_HOME": str(self.root)}):
            core = configured(parser().parse_args(["profiles"]))
            self.assertEqual(core.inventory, self.inventory)
            self.assertEqual(core.provider, "external")
            self.assertEqual(core.executable, str(FAKE))
            self.assertEqual(core.profiles, self.profiles)
            self.assertEqual(os.environ["PLAYWRIGHT_BROWSERS_PATH"], str(self.root / "browsers"))
            self.assertEqual(configured(parser().parse_args(["--provider", "skip", "profiles"])).provider, "skip")

    def test_cli_json_errors(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = main(["--unknown"])
        self.assertEqual(status, 1)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("error", json.loads(err.getvalue()))

    def test_cli_subprocess(self):
        result = subprocess.run([sys.executable, "-m", "web", "--inventory", str(self.inventory), "--profiles", str(self.profiles), "--state-dir", str(self.core.state), "--provider", "external", "--provider-command", str(FAKE), "inspect", "--device", "lab", "--profile", "fixture"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["values"]["model"], "fixture-router")

    def test_shipped_candidates(self):
        for path in (ROOT / "web" / "profiles").glob("*-candidate.json"):
            profile = validate_profile(json.loads(path.read_text()))
            self.assertEqual(profile["status"], "candidate")
            self.assertFalse(profile["read_only_reviewed"])

    def test_plan_rejects_invalid_vlan_and_credential_text(self):
        for vlan in (0, 4095, True, "20"):
            with self.assertRaises(Error):
                self.core.plan("lab", "fixture", "vlan.configure", {"vlan": vlan}, "console")
        with self.assertRaises(Error):
            self.core.plan("lab", "fixture", "vlan.configure", {"vlan": 20}, "fixture-password-unique")
        self.assertFalse(self.calls.exists())

    def test_operator_approval_requires_terminal(self):
        plan = self.make_plan()
        out, err = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {"NTN_HOME": str(self.root)}), patch("builtins.open", side_effect=OSError("no terminal")), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(main(["--state-dir", str(self.core.state), "approve", "--plan", plan["plan_id"]]), 1)
        self.assertFalse((self.core.state / (plan["plan_id"] + ".approval.json")).exists())

    def test_bundled_requires_explicit_authentication(self):
        from web.provider import read
        with self.assertRaisesRegex(Error, "explicit reviewed authentication"):
            read({"profile": self.p, "credentials": {"username": "fixture", "password": "test"}})

    def test_tls_policy_is_device_local_and_strict_by_default(self):
        self.core.provider = "bundled"
        for policy in ({}, {"tls_verify": False}, {"tls_verify": True}):
            web = dict(self.inv["devices"][0]["web"], **policy)
            with patch.object(self.core, "device", return_value=(self.inv["devices"][0], web, "https://lab.invalid")), patch("web.provider.read", return_value={"origin": "https://lab.invalid", "values": {"model": "fixture-router", "vlan": "10"}}) as read:
                self.core.inspect("lab", "fixture")
                self.assertIs(read.call_args.args[0]["policy"]["tls_verify"], policy.get("tls_verify", True))
        web = dict(web, tls_verify="false")
        with patch.object(self.core, "device", return_value=(self.inv["devices"][0], web, "https://lab.invalid")), self.assertRaisesRegex(Error, "explicit boolean"):
            self.core.inspect("lab", "fixture")

    def test_authentication_profiles_and_scope(self):
        for name in ("webfig-auth", "cdata-auth"):
            profile = validate_profile(json.loads((ROOT / "web/profiles" / (name + ".json")).read_text()))
            self.assertEqual(profile["status"], "reviewed")
            self.assertEqual(profile["review_scope"], "authentication-only")
            self.assertTrue(all(v == "unsupported" for v in profile["capabilities"].values()))
            profile["fields"]["vlan"] = "#vlan"
            with self.assertRaises(Error):
                validate_profile(profile)

    def test_authentication_validation(self):
        profile = json.loads((ROOT / "web/profiles/webfig-auth.json").read_text())
        for key, value in (("login_path", "//evil.invalid"), ("success_path", "/#"), ("success_text", ""), ("submit_selector", ""),
                           ("requests", [{"path": "/login", "query": "", "method": "DELETE", "max_requests": 1}]),
                           ("requests", [{"path": "/login", "query": "", "method": "POST", "max_requests": 0}])):
            p = json.loads(json.dumps(profile))
            p["authentication"][key] = value
            with self.assertRaises(Error):
                validate_profile(p)

    def test_authentication_only_cannot_plan(self):
        profile = json.loads((ROOT / "web/profiles/webfig-auth.json").read_text())
        with patch.object(self.core, "profile", return_value=profile), self.assertRaisesRegex(Error, "configuration baseline"):
            self.make_plan()
        self.assertFalse(self.calls.exists())

    def test_origin_validation(self):
        self.assertEqual(origin("https://LAB.invalid:443/"), "https://lab.invalid")
        for bad in ("file:///tmp/a", "https://u:p@host", "https://host/path", "https://host?x=1", "http://host:invalid", "//host"):
            with self.assertRaises((Error, ValueError)):
                origin(bad)


if __name__ == "__main__":
    unittest.main()
