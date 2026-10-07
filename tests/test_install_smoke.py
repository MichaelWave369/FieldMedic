import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fieldmedic import __version__
from fieldmedic.hashutil import sha256_json
from fieldmedic.install_smoke import (
    SMOKE_SCHEMA,
    install_smoke_gate_from_home,
    validate_install_smoke_receipt,
)


def receipt():
    observed = {
        "default_uninstall_program_removed": True,
        "default_uninstall_data_preserved": True,
        "sentinel_present_after_uninstall": True,
        "sentinel_present_after_reinstall": True,
        "sentinel_sha_before": "a" * 64,
        "sentinel_sha_after_uninstall": "a" * 64,
        "sentinel_sha_after_reinstall": "a" * 64,
        "reinstall_launcher_ok": True,
        "reinstall_discovery_ready": True,
    }
    body = {
        "schema": SMOKE_SCHEMA,
        "fieldmedic_version": __version__,
        "generated_at": "2026-10-07T00:00:00Z",
        "platform": {
            "os_name": "nt",
            "platform": "Windows-11",
            "machine": "AMD64",
        },
        "first_install_receipt_sha256": "b" * 64,
        "second_install_receipt_sha256": "c" * 64,
        "engine_versions": {
            "drivemedic": "DriveMedic 1.0.0-rc13",
            "netmedic": "Parallax NetMedic v0.34.0",
        },
        "observations": observed,
        "status": "PASS",
        "claim_boundary": "bounded local smoke",
    }
    return {**body, "receipt_sha256": sha256_json(body)}


class InstallSmokeTests(unittest.TestCase):
    def test_current_valid_smoke_receipt_is_admitted(self):
        valid, errors = validate_install_smoke_receipt(
            receipt(),
            expected_version=__version__,
        )
        self.assertTrue(valid)
        self.assertEqual(errors, [])

    def test_tampered_smoke_receipt_is_rejected(self):
        value = receipt()
        value["observations"]["sentinel_present_after_reinstall"] = False
        valid, errors = validate_install_smoke_receipt(
            value,
            expected_version=__version__,
        )
        self.assertFalse(valid)
        self.assertIn("install smoke receipt fingerprint mismatch", errors)

    def test_gate_reads_current_receipt(self):
        import json
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            path = home / "qualification" / "windows-install-smoke" / "latest.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(receipt()), encoding="utf-8")
            gate = install_smoke_gate_from_home(home)
            self.assertEqual(gate["status"], "QUALIFIED_BY_LOCAL_RECEIPT")


if __name__ == "__main__":
    unittest.main()
