"""Smoke tests: optional web dispatch must not initialize SSH inventory."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DispatchTests(unittest.TestCase):
    def run_ntn(self, home, *args):
        return subprocess.run(["bash", str(ROOT / "ntn"), *args],
                              env=dict(os.environ, NTN_HOME=home),
                              capture_output=True, text=True, timeout=15)

    def test_web_help_does_not_create_inventory(self):
        with tempfile.TemporaryDirectory() as home:
            result = self.run_ntn(home, "web", "--help")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("--profiles", result.stdout)
            self.assertFalse((Path(home) / "devices.json").exists())

    def test_capabilities_returns_json_without_device_access(self):
        with tempfile.TemporaryDirectory() as home:
            result = self.run_ntn(home, "web", "capabilities")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("onu.provision", json.loads(result.stdout))
            self.assertFalse((Path(home) / "devices.json").exists())

    def test_ssh_help_unchanged(self):
        with tempfile.TemporaryDirectory() as home:
            result = self.run_ntn(home, "help")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("ntn sync <ref|all>", result.stdout)
            data = json.loads((Path(home) / "devices.json").read_text())
            self.assertEqual(data["devices"], [])
            self.assertEqual(data["next_id"], 1)


if __name__ == "__main__":
    unittest.main()
