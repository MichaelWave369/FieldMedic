import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fieldmedic import __version__
from fieldmedic.hashutil import sha256_json
from fieldmedic.installation import INSTALL_SCHEMA
from fieldmedic.release_receipt import build_release_receipt


DISCOVERY = {
    "schema": "field-medic-engine-discovery-v1",
    "drivemedic": {
        "engine": "drivemedic",
        "path": "C:/DriveMedic/drivemedic.exe",
        "discovered_by": "config:engines.json",
        "present": True,
        "version": "DriveMedic 1.0.0-rc13",
        "healthy": True,
        "details": {},
        "errors": [],
    },
    "netmedic": {
        "engine": "netmedic",
        "path": "C:/NetMedic/netmedic.exe",
        "discovered_by": "config:engines.json",
        "present": True,
        "version": "Parallax NetMedic v0.34.0",
        "healthy": True,
        "details": {},
        "errors": [],
    },
    "engine_config": {"status": "CONFIGURED"},
    "ready_for_diagnostics": True,
}


def install_receipt():
    body = {
        "schema": INSTALL_SCHEMA,
        "fieldmedic_version": __version__,
        "installed_at": "2026-10-07T22:00:00Z",
        "platform": {
            "os_name": "nt",
            "platform": "Windows-11",
            "machine": "AMD64",
        },
        "home": "C:/Users/test/AppData/Local/FieldMedic",
        "install_root": "C:/Users/test/AppData/Local/Programs/FieldMedic",
        "runtime_root": "C:/Users/test/AppData/Local/Programs/FieldMedic/runtimes/current",
        "wheel": {
            "path": "C:/bundle/fieldmedic.whl",
            "size_bytes": 123,
            "sha256": "a" * 64,
        },
        "launchers": {
            "fieldmedic": "C:/Users/test/AppData/Local/Programs/FieldMedic/bin/fieldmedic.cmd",
            "dashboard": "C:/Users/test/AppData/Local/Programs/FieldMedic/bin/fieldmedic-dashboard.cmd",
        },
        "uninstaller": "C:/Users/test/AppData/Local/Programs/FieldMedic/uninstall.ps1",
        "path_added": False,
        "engine_config": {"status": "CONFIGURED"},
        "engine_discovery": DISCOVERY,
        "data_preserved_on_default_uninstall": True,
    }
    return {**body, "receipt_sha256": sha256_json(body)}


class ReleaseInstallGateTests(unittest.TestCase):
    def test_release_receipt_admits_current_hash_valid_install_handoff(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            root = home / "installation"
            root.mkdir(parents=True)
            (root / "install.json").write_text(
                json.dumps(install_receipt()),
                encoding="utf-8",
            )
            with patch(
                "fieldmedic.release_receipt.discover_engines",
                return_value=DISCOVERY,
            ):
                result = build_release_receipt(home=home)
        self.assertEqual(
            result["release_gates"]["windows_install_handoff"],
            "INSTALLED_BY_LOCAL_RECEIPT",
        )
        self.assertEqual(
            result["qualification_receipts"]["windows_install"]["status"],
            "INSTALLED_BY_LOCAL_RECEIPT",
        )


if __name__ == "__main__":
    unittest.main()
