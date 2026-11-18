"""JSON CLI. Approval issuance is deliberately outside MCP dispatch."""
import argparse
import json
import os
import sys
from pathlib import Path

from .core import Core, Error, canonical, load
from .mcp import serve


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Error("invalid command arguments; use --help")


def parser():
    p = Parser(description="Independent Web GUI core (read-only; vendor writes unsupported)")
    for arg in ("inventory", "profiles", "state-dir", "settings", "provider-command"):
        p.add_argument("--" + arg)
    p.add_argument("--provider", choices=("bundled", "playwright", "external", "skip"))
    p.add_argument("--allow-http-credentials", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("profiles", "capabilities", "mcp"):
        sub.add_parser(name)
    validate = sub.add_parser("validate-profile")
    validate.add_argument("profile", help="profile id under --profiles (no arbitrary paths)")
    for name in ("inspect", "learn", "plan"):
        s = sub.add_parser(name)
        s.add_argument("--device", required=True)
        s.add_argument("--profile", required=True)
        if name == "plan":
            s.add_argument("--action", required=True)
            s.add_argument("--params", required=True, help="JSON object; no secrets")
            s.add_argument("--recovery", required=True, help="operator recovery instructions; no secrets")
    for name in ("review", "approve", "apply", "rollback"):
        s = sub.add_parser(name)
        s.add_argument("--plan", required=True)
    return p


def configured(args):
    home = Path(os.environ.get("NTN_HOME", Path.home() / ".ntnroute"))
    settings_path = Path(args.settings) if args.settings else home / "web-settings.json"
    config = load(settings_path) if settings_path.exists() else {}
    if config and (not isinstance(config, dict) or config.get("version") != 1):
        raise Error("unsupported web settings")
    browser = config.get("browser", {})
    provider = args.provider or {"existing": "external", "bundled": "bundled", "skip": "skip"}.get(browser.get("provider", "skip"))
    if provider is None:
        raise Error("invalid configured provider")
    if config.get("browsers_path"):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = config["browsers_path"]
    return Core(args.inventory or home / "devices.json", args.profiles or config.get("profiles_dir", home / "web" / "profiles"), args.state_dir or config.get("state_dir", home / "web-state"), provider, args.provider_command or browser.get("executable"), args.allow_http_credentials)


def main(argv=None):
    try:
        args = parser().parse_args(argv)
        core = configured(args)
        command = args.command
        if command == "mcp":
            serve(core, sys.stdin, sys.stdout)
            return 0
        if command == "validate-profile":
            result = core.profile(args.profile)
        elif command == "approve":
            body = core.review(args.plan)
            # Neither a CLI boolean nor a public plan hash is proof of operator consent.
            # Open the controlling terminal, never stdin (which may be an MCP pipe).
            with open("/dev/tty", "r+") as tty:
                tty.write(canonical(body) + "\nReview-only plan, NO supported writes. Type 'approve " + args.plan + "': ")
                tty.flush()
                if tty.readline().strip() != "approve " + args.plan:
                    raise Error("operator approval declined")
            result = core.approve(args.plan)
        elif command in ("review", "apply", "rollback"):
            result = core.dispatch(command, {"plan_id": args.plan})
        elif command in ("inspect", "learn"):
            result = core.inspect(args.device, args.profile, learn=command == "learn")
            if command == "learn":
                result = {"kind": "read-only-candidate-observation", "trusted_profile": False, "observation": result, "limits": "reviewed fields and up to 64 controls (structural metadata only); no values, crawling or automatic profile promotion"}
        elif command == "plan":
            result = core.plan(args.device, args.profile, args.action, json.loads(args.params), args.recovery)
        else:
            result = core.dispatch(command, {})
        print(canonical(result))
        return 0
    except Exception as exc:
        message = str(exc) if isinstance(exc, Error) else "operation failed (invalid input, unavailable provider, file or operator terminal)"
        print(canonical({"error": message}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
