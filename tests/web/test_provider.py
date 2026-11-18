"""Loopback-only fixtures. No real inventory, router access or browser installs."""
import contextlib
import io
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from web.__main__ import main
from web.core import Error, canonical
from web.provider import Guard, read, same_origin

PROFILES = Path(__file__).resolve().parents[2] / "web/profiles"


def request(name="webfig-auth", target="http://localhost:12345"):
    profile = json.loads((PROFILES / (name + ".json")).read_text())
    # These endpoints belong ONLY to the loopback fixtures, not real devices.
    profile["asset_requests"] = [{"path": "/app.js", "query": "", "method": "GET", "max_requests": 1}]
    profile["authentication"]["requests"] = [
        {"path": path, "query": "", "method": "POST", "max_requests": 1}
        for path in ("/", "/login-api")]
    return {"method": "learn", "origin": target,
            "profile": profile,
            "credentials": {"username": "fixture-user", "password": "fixture-only-password"},
            "policy": {"tls_verify": True, "timeout_seconds": 1}}


class GuardTests(unittest.TestCase):
    def test_routes_and_frames(self):
        r = request()
        for login, url, method, kind, navigation, frame, allowed in [
            (False, "/", "GET", "document", True, "about:blank", True),
            (False, "/app.js", "GET", "script", False, r["origin"] + "/", True),
            (True, "/login-api", "POST", "fetch", False, r["origin"] + "/", True),
            (False, "/login-api", "POST", "fetch", False, r["origin"] + "/", False),
            (False, "/reset", "GET", "document", True, r["origin"] + "/", False),
            (False, "/reset", "GET", "fetch", False, r["origin"] + "/", False),
            (True, "http://elsewhere.invalid/", "POST", "fetch", False, r["origin"] + "/", False),
            (True, "/", "POST", "document", True, "https://elsewhere.invalid", False),
            (True, "/", "DELETE", "fetch", False, r["origin"] + "/", False),
        ]:
            with self.subTest(url=url, method=method, login=login, frame=frame):
                guard = Guard(r["origin"], r["profile"])
                guard.login = login
                route = Mock()
                route.request = SimpleNamespace(url=r["origin"] + url if url.startswith("/") else url,
                                                method=method, resource_type=kind,
                                                frame=SimpleNamespace(url=frame),
                                                is_navigation_request=lambda: navigation)
                route.fetch.return_value = SimpleNamespace(status=200, headers={})
                guard.route(route)
                self.assertEqual(route.fulfill.called, allowed)
                self.assertEqual(route.abort.called, not allowed)
                self.assertEqual(guard.blocked, not allowed)

    def test_undeclared_requests_and_query_variants_never_fetch(self):
        r = request()
        for path, method, kind, navigation in (
                ("/reset", "POST", "fetch", False),
                ("/reset", "GET", "xhr", False),
                ("/reset", "GET", "image", False),
                ("/login-api?reset=1", "POST", "fetch", False),
                ("/app.js?reset=1", "GET", "script", False),
                ("/", "POST", "document", True),
                ("/app.js", "POST", "script", False)):
            with self.subTest(path=path, kind=kind):
                r["profile"]["authentication"]["requests"] = [
                    {"path": "/login-api", "query": "", "method": "POST", "max_requests": 1}]
                guard = Guard(r["origin"], r["profile"])
                guard.login = True
                route = Mock()
                route.request = SimpleNamespace(url=r["origin"] + path, method=method,
                                                resource_type=kind, frame=SimpleNamespace(url=r["origin"] + "/"),
                                                is_navigation_request=lambda: navigation)
                guard.route(route)
                route.fetch.assert_not_called()
                route.abort.assert_called_once()

    def test_declared_request_counts_and_exact_query(self):
        r = request()
        for group, method, kind in (("assets", "GET", "script"), ("auth", "POST", "fetch")):
            profile = r["profile"]
            entries = profile["asset_requests"] if group == "assets" else profile["authentication"]["requests"]
            entries[:] = [{"path": "/known", "query": "v=1&x=2", "method": method, "max_requests": 2}]
            for query in ("?v=1&x=2", "", "?x=2&v=1", "?v=1&x=2&extra=3", "?v=%31&x=2"):
                guard = Guard(r["origin"], profile)
                guard.login = True
                for index in range(3):
                    route = Mock()
                    route.request = SimpleNamespace(url=r["origin"] + "/known" + query, method=method,
                                                    resource_type=kind, frame=SimpleNamespace(url=r["origin"] + "/"),
                                                    is_navigation_request=lambda: False)
                    route.fetch.return_value = SimpleNamespace(status=200, headers={})
                    guard.route(route)
                    self.assertEqual(route.fetch.called, query == "?v=1&x=2" and index < 2)

    def test_auth_document_get_cannot_bypass_declared_count(self):
        r = request()
        r["profile"]["authentication"]["requests"] = [
            {"path": "/", "query": "", "method": "GET", "max_requests": 1}]
        guard = Guard(r["origin"], r["profile"])
        guard.login = True
        for index in range(2):
            route = Mock()
            route.request = SimpleNamespace(url=r["origin"] + "/", method="GET", resource_type="document",
                                            frame=SimpleNamespace(url=r["origin"] + "/"),
                                            is_navigation_request=lambda: True)
            route.fetch.return_value = SimpleNamespace(status=200, headers={})
            guard.route(route)
            self.assertEqual(route.fetch.called, index == 0)

    def test_shipped_auth_without_endpoints_fails_before_browser(self):
        for name in ("webfig-auth", "cdata-auth"):
            r = request(name)
            r["profile"] = json.loads((PROFILES / (name + ".json")).read_text())
            with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(Error, "authentication requests"):
                read(r)

    def test_exact_origin(self):
        for url in ("https://lab.invalid.evil/", "https://lab.invalid:444/", "http://lab.invalid/", "https://user@lab.invalid/", "data:text/html,x"):
            self.assertFalse(same_origin(url, "https://lab.invalid"))
        self.assertTrue(same_origin("https://LAB.invalid:443/path#x", "https://lab.invalid"))

    def test_debug_is_rejected_without_secret_output(self):
        with patch.dict(os.environ, {"DEBUG": "pw:api"}), self.assertRaisesRegex(Error, "disable browser debugging") as exc:
            read(request())
        self.assertNotIn(request()["credentials"]["password"], str(exc.exception))

    def test_candidate_rejected_before_import(self):
        r = request()
        r["profile"]["status"] = "candidate"
        with self.assertRaisesRegex(Error, "candidate"):
            read(r)

    def test_redirect_hop_validated_before_credentials_can_follow(self):
        r = request()
        for destination, allowed in ((r["origin"] + "/webfig/", True), ("http://elsewhere.invalid/", False), (r["origin"] + "/reset", False)):
            guard = Guard(r["origin"], r["profile"])
            guard.login = True
            route = Mock()
            route.request = SimpleNamespace(url=r["origin"] + "/", method="POST", resource_type="document",
                                            frame=SimpleNamespace(url=r["origin"] + "/"), is_navigation_request=lambda: True)
            route.fetch.return_value = SimpleNamespace(status=303, headers={"location": destination})
            guard.route(route)
            route.fetch.assert_called_once_with(max_redirects=0, timeout=20000)
            self.assertEqual(route.fulfill.called, allowed)
            self.assertEqual(route.abort.called, not allowed)

    def test_browser_login_orchestration_tls_and_redacted_failure(self):
        import sys
        for verify in (True, False):
            r = request()
            r["policy"]["tls_verify"] = verify
            page, context, browser, runtime = Mock(), Mock(), Mock(), Mock()
            runtime.chromium.launch.return_value = browser
            browser.new_context.return_value = context
            context.new_page.return_value = page
            page.url = r["origin"] + "/webfig/"
            page.frames = [SimpleNamespace(url=page.url)]
            control = Mock()
            control.count.return_value = 1
            control.is_visible.return_value = True
            control.evaluate.side_effect = lambda expression: r["origin"] + "/" if "formAction" in expression else "Queues"
            control.evaluate_all.return_value = []
            page.locator.return_value = control
            factory = Mock()
            factory.return_value.__enter__ = Mock(return_value=runtime)
            factory.return_value.__exit__ = Mock(return_value=False)
            module = SimpleNamespace(sync_playwright=factory)
            with patch.dict(sys.modules, {"playwright": Mock(), "playwright.sync_api": module}), patch.dict(os.environ, {}, clear=True):
                result = read(r)
                self.assertEqual(result["values"], {"status": "Queues"})
                self.assertIs(browser.new_context.call_args.kwargs["ignore_https_errors"], not verify)
                self.assertIs(browser.new_context.call_args.kwargs["java_script_enabled"], True)
                self.assertEqual(control.fill.call_count, 2)
                control.click.assert_called_once()
                browser.close.assert_called_once()
                for secret in ('quote"secret', 'back\\secret', 'unicodé秘密', 'control\n\t\x01secret'):
                    r["credentials"]["password"] = secret
                    control.evaluate_all.return_value = [{"nested": ["prefix " + secret]}]
                    with self.assertRaisesRegex(Error, "credential material"):
                        read(r)
                control.evaluate_all.return_value = []
                control.fill.side_effect = RuntimeError(r["credentials"]["password"])
                with self.assertRaisesRegex(Error, "browser login/read failed") as exc:
                    read(r)
                self.assertNotIn(r["credentials"]["password"], str(exc.exception))

    def test_request_budget(self):
        r = request()
        guard = Guard(r["origin"], r["profile"])
        guard.requests = 256
        route = Mock()
        route.request = SimpleNamespace(url=r["origin"] + "/", frame=SimpleNamespace(url="about:blank"))
        guard.route(route)
        route.abort.assert_called_once()


class LoginBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise unittest.SkipTest("Playwright Python package unavailable; local browser login fixtures not run")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    context = browser.new_context()
                    if not hasattr(context, "route_web_socket"):
                        raise unittest.SkipTest("Playwright lacks required WebSocket routing support")
                finally:
                    browser.close()
        except unittest.SkipTest:
            raise
        except Exception:
            raise unittest.SkipTest("Playwright Chromium unavailable or cannot launch; no browser installed by tests")

    def setUp(self):
        self.mode = "webfig"
        self.posts = 0
        self.sink_hits = 0
        self.unreviewed_hits = 0
        owner = self

        class Sink(BaseHTTPRequestHandler):
            def do_GET(self):
                owner.sink_hits += 1
                self.send_response(200)
                self.end_headers()
            do_POST = do_GET
            def log_message(self, format, *args):
                pass

        self.sink = ThreadingHTTPServer(("127.0.0.1", 0), Sink)
        self.start_server(self.sink)
        self.off_origin = "http://127.0.0.1:" + str(self.sink.server_port)

        class Handler(BaseHTTPRequestHandler):
            def send(self, content):
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(content.encode())

            def do_GET(self):
                if self.path.startswith("/reset"):
                    owner.unreviewed_hits += 1
                    self.send("unexpected")
                    return
                if self.path == "/webfig/":
                    if "session=fixture" not in self.headers.get("Cookie", ""):
                        self.send("Login")
                    else:
                        self.send('<a href="#Queues">Queues</a>' + '<input value="fixture-only-password">' * 80)
                    return
                if owner.mode in ("cdata", "bad-marker", "wrong-url", "hidden", "echo"):
                    self.send('''<input type=text><input type=password><button onclick="login()">login</button>
<script>async function login() {
 await fetch('/login-api', {method:'POST', body: document.querySelector('input[type=password]').value});
 setTimeout(() => { location.hash = HASH;
 document.body.innerHTML = MARKUP; }, 100);
}</script>'''.replace("HASH", json.dumps("/wrong" if owner.mode == "wrong-url" else "/"))
                              .replace("MARKUP", json.dumps('<h1' + (' hidden' if owner.mode == "hidden" else '') + '>' +
                                                            ("Not Overview" if owner.mode == "bad-marker" else "Overview") + '</h1>' +
                                                            ('<div id="echo">fixture-only-password</div>' if owner.mode == "echo" else ''))))
                    return
                action = owner.off_origin + "/" if owner.mode == "off-form" else "/"
                script = "document.querySelector('form').submit()"
                if owner.mode == "off-js":
                    script = "fetch(" + json.dumps(owner.off_origin + "/") + ", {method:'POST',body:document.querySelector('#password').value})"
                if owner.mode == "same-origin-js":
                    script = "fetch('/reset', {method:'POST',body:document.querySelector('#password').value})"
                extra = '<iframe src="' + owner.off_origin + '/"></iframe>' if owner.mode == "off-frame" else ""
                if owner.mode == "same-origin-asset":
                    extra = '<img src="/reset?apply=1">'
                self.send('<form method="post" action="' + action + '"><input id="name"><input id="password" type="password">'
                          '<a onclick="dologin()">Login</a></form><script>function dologin(){' + script + '}</script>' + extra)

            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", "0")))  # never record body
                owner.posts += 1
                if self.path.startswith("/reset"):
                    owner.unreviewed_hits += 1
                if owner.mode == "redirect":
                    self.send_response(307)
                    self.send_header("Location", owner.off_origin + "/")
                elif self.path == "/login-api" or owner.mode == "http-only":
                    self.send_response(200)
                else:
                    self.send_response(303)
                    self.send_header("Location", "/webfig/")
                self.send_header("Set-Cookie", "session=fixture; HttpOnly; SameSite=Strict")
                self.end_headers()

            def log_message(self, format, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.start_server(self.server)
        self.target = "http://127.0.0.1:" + str(self.server.server_port)

    def start_server(self, server):
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join)
        self.addCleanup(server.shutdown)

    def test_webfig_login_and_bounded_controls(self):
        result = read(request(target=self.target))
        self.assertEqual(result["values"], {"status": "Queues"})
        self.assertEqual(len(result["controls"]), 64)
        self.assertNotIn("fixture-only-password", canonical(result))
        self.assertEqual(self.posts, 1)

    def test_cdata_javascript_login_waits_for_exact_marker(self):
        self.mode = "cdata"
        result = read(request("cdata-auth", self.target))
        self.assertEqual(result["values"], {"status": "Overview"})
        self.assertEqual(self.posts, 1)

    def test_http_success_wrong_url_hidden_and_wrong_text_are_not_login(self):
        for mode in ("http-only", "wrong-url", "hidden", "bad-marker"):
            self.mode = mode
            self.posts = 0
            with self.subTest(mode=mode), self.assertRaises(Error):
                read(request("webfig-auth" if mode == "http-only" else "cdata-auth", self.target))
            self.assertEqual(self.posts, 1)

    def test_off_origin_form_fetch_redirect_and_frame_never_reach_sink(self):
        for mode in ("off-form", "off-js", "redirect", "off-frame"):
            self.mode = mode
            with self.subTest(mode=mode), self.assertRaises(Error) as exc:
                read(request(target=self.target))
            self.assertNotIn("fixture-only-password", str(exc.exception))
            self.assertEqual(self.sink_hits, 0)

    def test_unreviewed_same_origin_requests_never_reach_server(self):
        for mode in ("same-origin-js", "same-origin-asset"):
            self.mode = mode
            with self.subTest(mode=mode), self.assertRaises(Error):
                read(request(target=self.target))
            self.assertEqual(self.unreviewed_hits, 0)
            self.assertEqual(self.posts, 0)

    def test_credential_echo_in_reviewed_field_is_rejected(self):
        self.mode = "echo"
        r = request("cdata-auth", self.target)
        r["profile"]["review_scope"] = "status"
        r["profile"]["fields"]["model"] = "#echo"
        with self.assertRaisesRegex(Error, "credential material"):
            read(r)

    def test_cli_learn_authenticated_metadata_and_inventory_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            inventory = Path(temp) / "devices.json"
            inventory.write_text(json.dumps({"next_id": 2, "checkpoints": [], "audit": [], "devices": [
                {"id": 1, "hostname": "fixture", "web": {"origin": self.target, "profile": "webfig-auth", **request()["credentials"]}}]}))
            profiles = Path(temp) / "profiles"
            profiles.mkdir()
            (profiles / "webfig-auth.json").write_text(json.dumps(request()["profile"]))
            before = inventory.read_bytes()
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                result = main(["--inventory", str(inventory), "--profiles", str(profiles), "--provider", "bundled",
                               "--allow-http-credentials", "learn", "--device", "fixture", "--profile", "webfig-auth"])
            self.assertEqual(result, 0, err.getvalue())
            observed = json.loads(out.getvalue())["observation"]
            self.assertEqual(observed["snapshot_kind"], "authentication-only")
            self.assertEqual(len(observed["controls"]), 64)
            self.assertNotIn("fixture-only-password", out.getvalue() + err.getvalue())
            self.assertEqual(inventory.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
