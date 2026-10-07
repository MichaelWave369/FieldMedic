import unittest

from fieldmedic import __version__
from fieldmedic.hashutil import sha256_json
from fieldmedic.install_smoke import (
    SMOKE_SCHEMA,
    validate_install_smoke_receipt,
)


def receipt(version=__version__):
    body = {
        "schema": SMOKE_SCHEMA,
        "fieldmedic_version": version,
        "generated_at": "2026-10-07T23:00:00Z",
        "status": "PASS",
        "platform": {
            "os_name": "nt",
            "platform": "Windows-11",
            "machine": "AMD64",
        },
        "bundle": {
            "path": "C:/bundle/FieldMedic.zip",
            "size_bytes": 1234,
            "sha256": "a" * 64,
        },
        "install_root": "C:/Temp/program",
        "data_root": "C:/Temp/data",
        "install_receipt_sha256": "b" * 64,
        "checks": {
            "install_completed": True,
            "discover_pass": True,
            "dashboard_pass": True,
            "release_receipt_pass": True,
            "default_uninstall_pass": True,
            "data_preserved": True,
            "sentinel_preserved": True,
            "program_removed": True,
        },
        "claim_boundary": "bounded smoke",
    }
    return {**body, "receipt_sha256": sha256_json(body)}


class InstallSmokeTests(unittest.TestCase):
    def test_complete_current_windows_smoke_is_valid(self):
        valid, errors = validate_install_smoke_receipt(
            receipt(),
            expected_version=__version__,
        )
        self.assertTrue(valid)
        self.assertEqual(errors, [])

    def test_missing_data_preservation_blocks_smoke(self):
        value = receipt()
        value["checks"]["data_preserved"] = False
        body = {k: v for k, v in value.items() if k != "receipt_sha256"}
        value["receipt_sha256"] = sha256_json(body)
        valid, errors = validate_install_smoke_receipt(
            value,
            expected_version=__version__,
        )
        self.assertFalse(valid)
        self.assertIn("install smoke check failed: data_preserved", errors)

    def test_old_version_smoke_does_not_promote_current_release(self):
        valid, errors = validate_install_smoke_receipt(
            receipt("0.7.0rc3"),
            expected_version=__version__,
        )
        self.assertFalse(valid)
        self.assertIn("install smoke FieldMedic version mismatch", errors)


if __name__ == "__main__":
    unittest.main()
