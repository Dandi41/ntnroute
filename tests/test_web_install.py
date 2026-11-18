"""Installer integration tests: all writes and commands stay in a temp sandbox."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import pty
import select
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]


class WebInstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ntn-install-test-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.repo = self.base / "repo"
        self.repo.mkdir()
        for name in ("install.sh", "install-web.sh"):
            if (ROOT / name).exists():
                shutil.copy2(ROOT / name, self.repo / name)
        self.home = self.base / "home"
        self.home.mkdir()
        self.ntn_home = self.home / "private ntn"
        self.bin = self.home / "bin"
        self.skills = self.home / ".hermes/skills/networking"
        self.fakebin = self.base / "fakebin"
        self.fakebin.mkdir()
        self.events = self.base / "events"
        self.script(self.repo / "ntn", '#!/bin/bash\nprintf "engine\\n" >> "$TEST_EVENTS"\n')
        (self.repo / "brands.json").write_text('{"brands":[]}\n')
        for name in ("curl", "wget", "pip", "pip3", "python3"):
            self.script(self.fakebin / name, '#!/bin/bash\nprintf "unexpected network/python command\\n" >> "$TEST_EVENTS"\nexit 91\n')
        self.env = {
            "HOME": str(self.home), "NTN_HOME": str(self.ntn_home),
            "BIN_DIR": str(self.bin), "HERMES_SKILLS": str(self.skills),
            "PATH": str(self.fakebin) + ":" + os.defpath,
            "TEST_EVENTS": str(self.events), "LC_ALL": "C",
        }

    def script(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        path.chmod(0o700)

    def run_install(self, *args):
        return subprocess.run(["bash", str(self.repo / "install.sh"), *args],
                              env=self.env, input="", text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)

    def assert_ok(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_dry_run_has_no_writes_even_with_hermes_and_bundled_choices(self):
        (self.home / ".hermes").mkdir()
        (self.repo / "web").mkdir()
        before = sorted(str(p.relative_to(self.home)) for p in self.home.rglob("*"))
        result = self.run_install("--dry-run", "--web", "bundled", "--mcp", "bundled")
        self.assert_ok(result)
        self.assertEqual(before, sorted(str(p.relative_to(self.home)) for p in self.home.rglob("*")))
        self.assertFalse(self.events.exists())

    def web_tree(self):
        (self.repo / "web/profiles").mkdir(parents=True)
        (self.repo / "web/__main__.py").write_text("# fixture module\n")
        (self.repo / "web/profiles/example.json").write_text('{"source":"repo"}')
        # Real Python only for version check; no package manager is reached.
        import sys
        self.script(self.fakebin / "python3", f'''#!{sys.executable}
import os, pathlib, shutil, sys
args = sys.argv[1:]
if args[:1] == ['-c']:
    exec(args[1])
elif args[:2] == ['-m', 'venv']:
    target = pathlib.Path(args[2]) / 'bin/python'
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(__file__, target)
else:
    with open(os.environ['TEST_EVENTS'], 'a') as out:
        out.write(' '.join(args) + '\\n')
        if args[:2] == ['-m', 'playwright']:
            out.write('cache=' + os.environ.get('PLAYWRIGHT_BROWSERS_PATH', '') + '\\n')
''')

    def test_existing_adapters_are_paths_not_executed_or_downloaded(self):
        self.web_tree()
        adapter = self.base / "trusted adapter"
        self.script(adapter, '#!/bin/bash\nexit 92\n')
        result = self.run_install("--web", "existing", "--web-adapter", str(adapter),
                                  "--mcp", "existing", "--mcp-adapter", str(adapter))
        self.assert_ok(result)
        config = json.loads((self.ntn_home / "web-settings.json").read_text())
        self.assertEqual(config["browser"]["executable"], str(adapter))
        self.assertEqual(config["mcp"]["executable"], str(adapter))
        self.assertEqual(self.events.read_text(), "engine\n")
        self.assertEqual((self.ntn_home / "web-settings.json").stat().st_mode & 0o777, 0o600)
        self.assertTrue((self.ntn_home / "web/__main__.py").exists())

    def test_bundled_browser_selection_alone_triggers_private_download_commands(self):
        self.web_tree()
        result = self.run_install("--web", "bundled", "--mcp", "skip")
        self.assert_ok(result)
        events = self.events.read_text()
        self.assertIn("-m pip install playwright\n", events)
        self.assertIn("-m playwright install chromium\n", events)
        self.assertIn("cache=" + str(self.ntn_home / "browsers"), events)
        config = json.loads((self.ntn_home / "web-settings.json").read_text())
        self.assertEqual(config["mcp"]["provider"], "skip")
        self.assertEqual(config["python"], str(self.ntn_home / "web-venv/bin/python"))

    def test_mcp_bundled_is_independent_and_preserves_profile_edits(self):
        self.web_tree()
        self.assert_ok(self.run_install("--web", "skip", "--mcp", "bundled"))
        profile = self.ntn_home / "web/profiles/example.json"
        profile.write_text('{"user":"edited"}')
        self.assert_ok(self.run_install("--web", "skip", "--mcp", "bundled"))
        self.assertEqual(profile.read_text(), '{"user":"edited"}')
        self.assertEqual(self.events.read_text(), "engine\nengine\n")
        config = json.loads((self.ntn_home / "web-settings.json").read_text())
        self.assertEqual(config["browser"]["provider"], "skip")
        self.assertEqual(config["mcp"]["provider"], "bundled")

    def existing_settings(self):
        self.ntn_home.mkdir(parents=True, exist_ok=True)
        config = {
            "version": 1,
            "browser": {"provider": "existing", "executable": "/custom/browser",
                        "protocol": "ntn-web-provider/1", "user_option": "browser"},
            "mcp": {"provider": "existing", "executable": "/custom/mcp",
                    "protocol": "mcp-stdio", "user_option": "mcp"},
            "python": str(self.base / "custom python"),
            "profiles_dir": str(self.base / "custom profiles"),
            "state_dir": str(self.base / "custom state"),
            "browsers_path": str(self.base / "custom browsers"),
            "user_option": {"keep": True},
        }
        # Preserved settings are data, never commands to execute during install.
        self.script(Path(config["python"]),
                    '#!/bin/bash\nprintf "unexpected custom python\\n" >> "$TEST_EVENTS"\nexit 93\n')
        (self.ntn_home / "web-settings.json").write_text(json.dumps(config))
        return config

    def test_selecting_one_component_preserves_other_and_custom_settings(self):
        self.web_tree()
        adapter = self.base / "replacement adapter"
        self.script(adapter, '#!/bin/bash\nexit 92\n')
        for component, key in (("web", "browser"), ("mcp", "mcp")):
            for provider in ("existing", "bundled"):
                with self.subTest(component=component, provider=provider):
                    original = self.existing_settings()
                    args = ["--web", "skip", "--mcp", "skip",
                            "--" + component, provider]
                    if provider == "existing":
                        args += ["--" + component + "-adapter", str(adapter)]
                    if self.events.exists():
                        self.events.unlink()
                    result = self.run_install(*args)
                    self.assert_ok(result)
                    expected = json.loads(json.dumps(original))
                    expected[key].update(provider=provider,
                                         executable=str(adapter) if provider == "existing" else "")
                    if component == "web" and provider == "bundled":
                        expected["python"] = str(self.ntn_home / "web-venv/bin/python")
                        expected["browsers_path"] = str(self.ntn_home / "browsers")
                    settings = self.ntn_home / "web-settings.json"
                    self.assertEqual(json.loads(settings.read_text()), expected)
                    self.assertEqual(settings.stat().st_mode & 0o777, 0o600)
                    events = self.events.read_text()
                    self.assertNotIn("unexpected", events)
                    if component == "web" and provider == "bundled":
                        self.assertIn("cache=" + expected["browsers_path"], events)
                    else:
                        self.assertEqual(events, "engine\n")

    def test_mcp_selection_preserves_bundled_browser_runtime(self):
        self.web_tree()
        self.assert_ok(self.run_install("--web", "bundled"))
        settings = self.ntn_home / "web-settings.json"
        original = json.loads(settings.read_text())
        self.events.unlink()
        self.assert_ok(self.run_install("--mcp", "bundled"))
        original["mcp"]["provider"] = "bundled"
        self.assertEqual(json.loads(settings.read_text()), original)
        self.assertEqual(self.events.read_text(), "engine\n")

    def test_invalid_existing_settings_fail_safely_before_writes(self):
        self.web_tree()
        valid = self.existing_settings()
        secret = "PRIVATE_SETTINGS_SENTINEL"
        invalid = ["", secret, '{"' + secret + '":', "null", "[]", "42",
                   json.dumps(valid) + "\n" + json.dumps(valid)]
        for key, value in (("version", 2), ("browser", []), ("mcp", None),
                           ("python", []), ("profiles_dir", False),
                           ("state_dir", {}), ("browsers_path", 42)):
            invalid.append(json.dumps(dict(valid, **{key: value, "private": secret})))
        for key in ("browser", "mcp"):
            for field, value in (("provider", "unknown"), ("executable", []),
                                 ("protocol", "unknown")):
                component = dict(valid[key], **{field: value})
                invalid.append(json.dumps(dict(valid, **{key: component, "private": secret})))
        settings = self.ntn_home / "web-settings.json"
        for index, text in enumerate(invalid):
            with self.subTest(case=index):
                settings.write_text(text)
                before = {str(p.relative_to(self.home)): p.read_bytes()
                          for p in self.home.rglob("*") if p.is_file()}
                result = self.run_install("--web", "bundled", "--mcp", "bundled")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("invalid existing web settings", result.stderr)
                self.assertNotIn(secret, result.stdout + result.stderr)
                after = {str(p.relative_to(self.home)): p.read_bytes()
                         for p in self.home.rglob("*") if p.is_file()}
                self.assertEqual(after, before)
                self.assertFalse(self.events.exists())
                self.assertFalse(self.bin.exists())
                self.assertFalse(list(self.ntn_home.glob(".web-settings.*")))

    def test_sparse_skipped_component_is_preserved_exactly(self):
        self.web_tree()
        self.ntn_home.mkdir()
        settings = self.ntn_home / "web-settings.json"
        original = {"version": 1, "browser": {"provider": "skip", "user_option": True},
                    "python": ""}
        settings.write_text(json.dumps(original))
        self.assert_ok(self.run_install("--mcp", "bundled"))
        config = json.loads(settings.read_text())
        self.assertEqual(config["browser"], original["browser"])
        self.assertEqual(config["python"], str(self.fakebin / "python3"))
        self.assertEqual(config["profiles_dir"], str(self.ntn_home / "web/profiles"))
        self.assertEqual(config["state_dir"], str(self.ntn_home / "web-state"))
        self.assertEqual(config["browsers_path"], str(self.ntn_home / "browsers"))
        self.assertEqual(self.events.read_text(), "engine\n")

    def test_skip_preserves_existing_settings_and_brands(self):
        self.ntn_home.mkdir()
        settings = self.ntn_home / "web-settings.json"
        settings.write_text('{"user":"managed"}')
        brands = self.ntn_home / "brands.json"
        brands.write_text('{"user":"brands"}')
        self.assert_ok(self.run_install("--non-interactive"))
        self.assertEqual(settings.read_text(), '{"user":"managed"}')
        self.assertEqual(brands.read_text(), '{"user":"brands"}')

    def test_dry_run_preserves_existing_manifest_and_local_edits(self):
        src = self.repo / "skills/ntnroute/SKILL.md"
        src.parent.mkdir(parents=True)
        src.write_text("repo content\n")
        self.skills.mkdir(parents=True)
        self.assert_ok(self.run_install())
        dest = self.skills / "ntnroute/SKILL.md"
        dest.write_text("local content\n")
        before = {str(p.relative_to(self.home)): p.read_bytes()
                  for p in self.home.rglob("*") if p.is_file()}
        self.events.unlink()
        self.assert_ok(self.run_install("--dry-run", "--web", "skip", "--mcp", "skip"))
        after = {str(p.relative_to(self.home)): p.read_bytes()
                 for p in self.home.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertFalse(self.events.exists())

    def test_default_noninteractive_skips_without_settings_or_downloads(self):
        self.assert_ok(self.run_install())
        self.assertFalse((self.ntn_home / "web-settings.json").exists())
        self.assertEqual(self.events.read_text(), "engine\n")

    def test_invalid_options_and_adapters_fail_before_writes(self):
        for args in [("--unknown",), ("--web",), ("--web", "bad"),
                     ("--web", "existing"), ("--mcp", "existing", "--mcp-adapter", "relative"),
                     ("--web-adapter", "/not/used")]:
            with self.subTest(args=args):
                result = self.run_install(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.ntn_home.exists())
                self.assertFalse(self.bin.exists())
                self.assertFalse(self.events.exists())

    def test_help_no_writes(self):
        result = self.run_install("--help")
        self.assert_ok(result)
        self.assertIn("ntn-web-provider/1", result.stdout)
        self.assertIn("--mcp", result.stdout)
        self.assertFalse(self.ntn_home.exists())

    def test_manifest_sync_preserves_authored_files_and_backs_up_edits(self):
        src = self.repo / "skills/ntnroute/SKILL.md"
        src.parent.mkdir(parents=True)
        src.write_text("initial\n")
        self.skills.mkdir(parents=True)
        self.assert_ok(self.run_install())
        dest = self.skills / "ntnroute/SKILL.md"
        dest.write_text("local edit\n")
        authored = self.skills / "ntnroute/authored.md"
        authored.write_text("keep me\n")
        src.write_text("updated\n")
        self.assert_ok(self.run_install())
        self.assertEqual(dest.read_text(), "updated\n")
        self.assertEqual(authored.read_text(), "keep me\n")
        copies = list(dest.parent.glob("SKILL.md.local-*"))
        self.assertEqual(len(copies), 1)
        self.assertEqual(copies[0].read_text(), "local edit\n")
        self.assertIn("ntnroute/SKILL.md", (self.skills / ".ntn_manifest").read_text())
        src.unlink()
        self.assert_ok(self.run_install("--force"))
        self.assertFalse(dest.exists())
        self.assertTrue(authored.exists())

    def test_interactive_prompts_ask_browser_and_mcp_separately(self):
        master, slave = pty.openpty()
        proc = subprocess.Popen(["bash", str(self.repo / "install.sh")], env=self.env,
                                stdin=slave, stdout=slave, stderr=slave)
        os.close(slave)
        output = b""
        sent_browser = sent_mcp = False
        deadline = time.monotonic() + 10
        try:
            while time.monotonic() < deadline:
                if select.select([master], [], [], 0.1)[0]:
                    try:
                        output += os.read(master, 65536)
                    except OSError:
                        break
                    if b"Browser backend" in output and not sent_browser:
                        os.write(master, b"skip\n")
                        sent_browser = True
                    if b"MCP integration" in output and not sent_mcp:
                        os.write(master, b"skip\n")
                        sent_mcp = True
                if proc.poll() is not None:
                    break
            self.assertEqual(proc.wait(timeout=2), 0, output.decode())
            self.assertTrue(sent_browser and sent_mcp, output.decode())
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            os.close(master)

    def test_noninteractive_explicit_skips_keep_ssh_install(self):
        result = self.run_install("--non-interactive", "--web", "skip", "--mcp", "skip")
        self.assert_ok(result)
        self.assertTrue((self.ntn_home / "ntn").is_file())
        self.assertFalse((self.ntn_home / "web-settings.json").exists())
        self.assertEqual(self.events.read_text(), "engine\n")


if __name__ == "__main__":
    unittest.main()
