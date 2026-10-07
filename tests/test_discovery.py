import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import subprocess

from fieldmedic.discovery import (
    probe_drivemedic,
    probe_netmedic,
)


class DiscoveryTests(unittest.TestCase):
    def test_missing_engine_is_explicit(self):
        with patch("fieldmedic.discovery._select", return_value=(None, None)):
            result = probe_drivemedic()
        self.assertFalse(result.present)
        self.assertIsNone(result.healthy)
        self.assertTrue(result.errors)

    def test_drivemedic_uses_declared_version_and_self_check_interfaces(self):
        with tempfile.TemporaryDirectory() as td:
            binary = Path(td) / "drivemedic.exe"
            binary.write_bytes(b"x")
            calls = []

            def fake_run(path, args, timeout=20):
                calls.append(args)
                if args == ["version"]:
                    return subprocess.CompletedProcess(
                        [str(path), *args], 0, "DriveMedic 1.0.0-rc13\n", ""
                    )
                return subprocess.CompletedProcess(
                    [str(path), *args],
                    0,
                    json.dumps({"ok": True, "checks": []}),
                    "",
                )

            with patch(
                "fieldmedic.discovery._select",
                return_value=(binary, "explicit"),
            ), patch("fieldmedic.discovery._run", side_effect=fake_run):
                result = probe_drivemedic()
            self.assertEqual(calls, [["version"], ["self-check-json"]])
            self.assertTrue(result.present)
            self.assertTrue(result.healthy)
            self.assertIn("1.0.0-rc13", result.version)

    def test_netmedic_uses_declared_version_and_crypto_status_interfaces(self):
        with tempfile.TemporaryDirectory() as td:
            binary = Path(td) / "netmedic.exe"
            binary.write_bytes(b"x")
            calls = []

            def fake_run(path, args, timeout=20):
                calls.append(args)
                if args == ["--version"]:
                    return subprocess.CompletedProcess(
                        [str(path), *args], 0, "Parallax NetMedic v0.34.0\n", ""
                    )
                return subprocess.CompletedProcess(
                    [str(path), *args], 0, "crypto backend available\n", ""
                )

            with patch(
                "fieldmedic.discovery._select",
                return_value=(binary, "explicit"),
            ), patch("fieldmedic.discovery._run", side_effect=fake_run):
                result = probe_netmedic()
            self.assertEqual(calls, [["--version"], ["--crypto-status"]])
            self.assertTrue(result.healthy)
            self.assertIn("0.34.0", result.version)


if __name__ == "__main__":
    unittest.main()
