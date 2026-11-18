"""Ephemeral, origin-locked Playwright login and bounded DOM inspection.

Only the reviewed login control is clicked. No crawling, configuration submits,
state export, console forwarding, screenshots, HAR or tracing. Authentication
traffic is allowed only during that control's single bounded login attempt.
"""
import html
import os
import time
from urllib.parse import urljoin, urlsplit

from .core import Error, contains_credentials, origin, require_auth_requests, validate_profile


def same_origin(url, target):
    try:
        parts = urlsplit(url)
        return origin(parts.scheme + "://" + parts.netloc) == target
    except (Error, ValueError):
        return False


class Guard:
    def __init__(self, target, profile):
        validate_profile(profile)
        self.target = target
        auth = profile.get("authentication", {})
        self.documents = {target + path.split("#", 1)[0] for path in
                          (profile["read_path"], auth.get("login_path", profile["read_path"]),
                           auth.get("success_path", profile["read_path"]))}
        self.assets = self.declarations(profile["asset_requests"])
        self.authentication = self.declarations(auth.get("requests", []))
        self.login = False
        self.blocked = False
        self.requests = 0

    def declarations(self, entries):
        return {(self.target + e["path"] + ("?" + e["query"] if e["query"] else ""), e["method"]):
                e["max_requests"] for e in entries}

    @staticmethod
    def consume(entries, req):
        key = (req.url, req.method)
        if entries.get(key, 0) <= 0:
            return False
        entries[key] -= 1
        return True

    def route(self, route):
        req = route.request
        self.requests += 1
        allowed = not self.blocked and same_origin(req.url, self.target) and self.requests <= 256
        try:
            frame_url = req.frame.url
            allowed = allowed and (frame_url == "about:blank" or same_origin(frame_url, self.target))
        except Exception:
            allowed = False  # worker traffic has no authorized frame
        if allowed:
            if req.is_navigation_request():
                if self.login and (req.url, req.method) in self.authentication:
                    allowed = self.consume(self.authentication, req)
                else:
                    allowed = req.method == "GET" and req.url in self.documents
            elif req.resource_type in ("script", "stylesheet", "image", "font"):
                allowed = self.consume(self.assets, req)
            else:
                allowed = self.login and req.resource_type in ("xhr", "fetch") and self.consume(self.authentication, req)
        if allowed:
            # Browser routing does not reliably intercept every redirect hop.
            # Fetch exactly one hop, validate Location, then expose the response.
            try:
                response = route.fetch(max_redirects=0, timeout=20000)
                if 300 <= response.status < 400:
                    location = response.headers.get("location", "")
                    destination = urljoin(req.url, location)
                    if (not location or not same_origin(destination, self.target) or destination not in self.documents
                            or not req.is_navigation_request() or req.method == "POST" and response.status not in (301, 302, 303)):
                        self.blocked = True
                        route.abort()
                        return
                    # Do not let Chromium follow an unintercepted redirect chain.
                    # A fresh GET navigation re-enters the guard; POST-preserving
                    # redirects and API redirects are deliberately unsupported.
                    route.fulfill(status=200, content_type="text/html", body=
                                  '<meta http-equiv="refresh" content="0;url=' + html.escape(destination, quote=True) + '">')
                    return
                route.fulfill(response=response)
            except Exception:
                self.blocked = True
                route.abort()
        else:
            self.blocked = True
            route.abort()

    def check(self, page):
        if self.blocked or not same_origin(page.url, self.target) or any(
                f.url != "about:blank" and not same_origin(f.url, self.target) for f in page.frames):
            raise Error("browser origin or reviewed request policy violation")


# Only fixed enumerations and DOM position are returned, not values, labels,
# hrefs, IDs, names, arbitrary attributes, HTML, or device-authored text.
CONTROLS = """els => els.slice(0, 64).map((e, index) => ({
    index, tag: e.tagName.toLowerCase(),
    type: ['text','password','checkbox','radio','submit','button','number','hidden'].includes(e.type) ? e.type : 'other',
    visible: !!(e.getClientRects().length), disabled: !!e.disabled
}))"""
TEXT = """e => {
    if (e.matches('input,textarea,select') || e.querySelector('input,textarea,select')) return null;
    const text = (e.textContent || '').trim();
    return text.length <= 2048 ? text : null;
}"""


def read(request):
    profile = validate_profile(request["profile"])
    if profile["status"] != "reviewed" or not profile["read_only_reviewed"]:
        raise Error("candidate profile cannot connect")
    require_auth_requests(profile)
    auth = profile.get("authentication")
    credentials = request["credentials"]
    if any(credentials.values()) and not auth:
        raise Error("explicit reviewed authentication selectors required")
    # Playwright debug channels can include fill arguments. Never run with them.
    if any(os.environ.get(key) for key in ("DEBUG", "PWDEBUG", "PW_API_DEBUG", "PW_TRACE_DIR")):
        raise Error("disable browser debugging/tracing before credential use")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise Error("optional Playwright is not installed") from None
    target = origin(request["origin"])
    policy = request["policy"]
    if type(policy["tls_verify"]) is not bool:
        raise Error("invalid TLS policy")
    timeout = min(20, max(1, policy["timeout_seconds"])) * 1000
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context(ignore_https_errors=not policy["tls_verify"],
                                              service_workers="block", java_script_enabled=True,
                                              accept_downloads=False)
                context.set_default_timeout(timeout)
                guard = Guard(target, profile)
                context.route("**/*", guard.route)
                # WebSockets bypass HTTP routing; fail closed on older Playwright.
                if not hasattr(context, "route_web_socket"):
                    raise Error("Playwright with WebSocket routing support required")
                context.route_web_socket("**/*", lambda ws: ws.close())
                page = context.new_page()
                page.on("dialog", lambda dialog: dialog.dismiss())
                context.on("page", lambda popup: popup.close())
                page.goto(target + (auth["login_path"] if auth else profile["read_path"]),
                          wait_until="domcontentloaded", timeout=timeout)
                guard.check(page)
                if auth:
                    controls = [page.locator(auth[key]) for key in
                                ("username_selector", "password_selector", "submit_selector")]
                    for control in controls:
                        control.wait_for(state="visible", timeout=timeout)
                        if control.count() != 1:
                            raise Error("login selector must match exactly one visible control")
                    # Check resolved form actions, including button overrides and
                    # <base> URLs, BEFORE filling any credential. Routes also
                    # guard JS fetch/submit/redirect changes after this check.
                    for control in controls:
                        destination = control.evaluate("e => e.hasAttribute('formaction') ? e.formAction : (e.form ? e.form.action : location.href)")
                        if not same_origin(destination, target):
                            raise Error("off-origin credential submission rejected")
                    guard.check(page)
                    controls[0].fill(credentials["username"])
                    controls[1].fill(credentials["password"])
                    guard.login = True
                    controls[2].click(no_wait_after=True, timeout=timeout)
                    deadline = time.monotonic() + timeout / 1000
                    marker = page.locator(auth["success_selector"])
                    while True:
                        guard.check(page)
                        if (page.url == target + auth["success_path"] and marker.count() == 1
                                and marker.is_visible() and marker.evaluate(TEXT) == auth["success_text"]):
                            break
                        if time.monotonic() >= deadline:
                            raise Error("authentication success markers not observed; no retry performed")
                        page.wait_for_timeout(50)
                    guard.login = False
                    if profile["read_path"] != auth["success_path"]:
                        page.goto(target + profile["read_path"], wait_until="domcontentloaded", timeout=timeout)
                values = {}
                for name, selector in profile["fields"].items():
                    field = page.locator(selector)
                    field.wait_for(state="visible", timeout=timeout)
                    if field.count() != 1:
                        raise Error("read selector must match exactly one visible element")
                    value = field.evaluate(TEXT)
                    if value is None:
                        raise Error("unsafe or oversized read field")
                    values[name] = value
                result = {"origin": target, "values": values}
                if request["method"] == "learn":
                    result["controls"] = page.locator("input,button,select,textarea,a").evaluate_all(CONTROLS)
                guard.check(page)
                if page.url != target + profile["read_path"]:
                    raise Error("unexpected status URL")
                if any(values[k] != v for k, v in profile["identity"].items()):
                    raise Error("exact status identity marker mismatch")
                if contains_credentials(result, credentials.values()):
                    raise Error("provider returned credential material")
                return result
            finally:
                browser.close()
    except Error:
        raise
    except Exception:
        # Playwright exceptions may include selectors, URLs and fill arguments.
        raise Error("browser login/read failed; no retry performed") from None
