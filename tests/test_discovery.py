import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import subprocess

from fieldmedic.discovery import (
    discover_engines,
    probe_drivemedic,
    probe_netmedic,
)
from fieldmedic.settings import write_engine_config


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

    def test_hash_bound_config_is_used_before_path_search(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            home = root / "home"
            drive = root / "drivemedic.exe"
            net = root / "netmedic.exe"
            drive.write_bytes(b"x")
            net.write_bytes(b"x")
            write_engine_config(
                home=home,
                drivemedic=str(drive),
                netmedic=str(net),
            )

            def fake_run(path, args, timeout=20):
                if args in (["version"], ["--version"]):
                    text = (
                        "DriveMedic 1.0.0-rc13\n"
                        if Path(path) == drive
                        else "Parallax NetMedic v0.34.0\n"
                    )
                    return subprocess.CompletedProcess([str(path), *args], 0, text, "")
                if args == ["self-check-json"]:
                    return subprocess.CompletedProcess(
                        [str(path), *args], 0, '{"ok":true}', ""
                    )
                return subprocess.CompletedProcess(
                    [str(path), *args], 0, "crypto available", ""
                )

            with patch("fieldmedic.discovery._run", side_effect=fake_run), patch(
                "fieldmedic.discovery.shutil.which",
                return_value=None,
            ):
                result = discover_engines(home=home)
            self.assertEqual(
                result["drivemedic"]["discovered_by"],
                "config:engines.json",
            )
            self.assertEqual(
                result["netmedic"]["discovered_by"],
                "config:engines.json",
            )
            self.assertTrue(result["ready_for_diagnostics"])

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
