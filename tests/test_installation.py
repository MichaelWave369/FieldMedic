import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fieldmedic import __version__
from fieldmedic.hashutil import sha256_json
from fieldmedic.installation import (
    INSTALL_SCHEMA,
    install_gate_from_home,
    validate_install_receipt,
)


def receipt(version=__version__):
    body = {
        "schema": INSTALL_SCHEMA,
        "fieldmedic_version": version,
        "installed_at": "2026-10-07T22:00:00Z",
        "platform": {
            "os_name": "nt",
            "platform": "Windows-11",
            "machine": "AMD64",
        },
        "home": "C:/Users/test/AppData/Local/FieldMedic",
        "install_root": "C:/Users/test/AppData/Local/Programs/FieldMedic",
        "runtime_root": "C:/Users/test/AppData/Local/Programs/FieldMedic/runtimes/0.7.0rc3",
        "wheel": {
            "path": "C:/bundle/fieldmedic.whl",
            "size_bytes": 123,
            "sha256": "a" * 64,
        },
        "launchers": {
            "fieldmedic": "C:/Users/test/AppData/Local/Programs/FieldMedic/bin/fieldmedic.cmd",
            "dashboard": "C:/Users/test/AppData/Local/Programs/FieldMedic/bin/fieldmedic-dashboard.cmd",
        },
        "path_added": False,
        "engine_config": {"status": "CONFIGURED"},
        "engine_discovery": {"ready_for_diagnostics": True},
        "data_preserved_on_default_uninstall": True,
    }
    return {**body, "receipt_sha256": sha256_json(body)}


class InstallationTests(unittest.TestCase):
    def test_current_windows_install_receipt_is_valid(self):
        valid, errors = validate_install_receipt(
            receipt(),
            expected_version=__version__,
        )
        self.assertTrue(valid)
        self.assertEqual(errors, [])

    def test_old_version_install_receipt_does_not_promote_current_release(self):
        valid, errors = validate_install_receipt(
            receipt("0.7.0rc2"),
            expected_version=__version__,
        )
        self.assertFalse(valid)
        self.assertIn("install receipt FieldMedic version mismatch", errors)

    def test_tampered_install_receipt_is_rejected(self):
        value = receipt()
        value["path_added"] = True
        valid, errors = validate_install_receipt(
            value,
            expected_version=__version__,
        )
        self.assertFalse(valid)
        self.assertIn("install receipt fingerprint mismatch", errors)

    def test_home_gate_reads_only_hash_valid_current_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            target = home / "installation"
            target.mkdir(parents=True)
            (target / "install.json").write_text(
                json.dumps(receipt()),
                encoding="utf-8",
            )
            result = install_gate_from_home(home)
            self.assertEqual(result["status"], "INSTALLED_BY_LOCAL_RECEIPT")


if __name__ == "__main__":
    unittest.main()
