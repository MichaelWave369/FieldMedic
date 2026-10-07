import json
import tempfile
import unittest
from pathlib import Path

from fieldmedic import __version__
from fieldmedic.hashutil import sha256_json
from fieldmedic.windows_qualification import (
    QUALIFICATION_SCHEMA,
    qualification_gate_from_home,
    validate_windows_qualification_receipt,
)


def pass_receipt(version: str = __version__):
    body = {
        "schema": QUALIFICATION_SCHEMA,
        "qualification_id": "winqual-test",
        "fieldmedic_version": version,
        "generated_at": "2026-10-07T21:00:00Z",
        "status": "PASS",
        "case_id": "case-winqual-test",
        "operator_label": "operator",
        "operator_label_semantics": "test",
        "platform": {
            "os_name": "nt",
            "platform": "Windows-11",
            "machine": "AMD64",
            "python": "3.13",
            "admin": True,
        },
        "engine_discovery": {
            "drivemedic": {
                "present": True,
                "healthy": True,
                "version": "DriveMedic 1.0.0-rc13",
                "path": "C:/DriveMedic/drivemedic.exe",
            },
            "netmedic": {
                "present": True,
                "healthy": True,
                "version": "Parallax NetMedic v0.34.0",
                "path": "C:/NetMedic/netmedic.exe",
            },
        },
        "requested_interface_test": {
            "interface_index": 12,
            "address_family": "IPv4",
            "temporary_metric": 50,
        },
        "tests": {
            "windows.process.priority": {
                "status": "PASS",
                "rollback_exact": True,
                "rollback_verification_status": "CAPTURED",
                "verification_status": "MEASURED_PENDING_OPERATOR_OUTCOME",
                "execution_evidence_id": "ev-exec-process",
                "verification_evidence_id": "ev-verify-process",
                "rollback_evidence_id": "ev-rollback-process",
            },
            "windows.interface.metric": {
                "status": "PASS",
                "rollback_exact": True,
                "verification_status": "MEASURED_PENDING_OPERATOR_OUTCOME",
                "execution_evidence_id": "ev-exec-interface",
                "verification_evidence_id": "ev-verify-interface",
                "rollback_evidence_id": "ev-rollback-interface",
            },
        },
        "errors": [],
        "claim_boundary": "bounded test",
    }
    return {**body, "receipt_sha256": sha256_json(body)}


class WindowsQualificationTests(unittest.TestCase):
    def test_valid_current_version_pass_receipt_is_admitted(self):
        valid, errors = validate_windows_qualification_receipt(
            pass_receipt(),
            expected_version=__version__,
        )
        self.assertTrue(valid)
        self.assertEqual(errors, [])

    def test_old_version_receipt_does_not_carry_forward(self):
        valid, errors = validate_windows_qualification_receipt(
            pass_receipt("0.6.0"),
            expected_version=__version__,
        )
        self.assertFalse(valid)
        self.assertIn(
            "qualification FieldMedic version mismatch",
            errors,
        )

    def test_forged_pass_without_exact_rollback_is_rejected(self):
        receipt = pass_receipt()
        receipt["tests"]["windows.interface.metric"]["rollback_exact"] = False
        body = {
            key: value for key, value in receipt.items()
            if key != "receipt_sha256"
        }
        receipt["receipt_sha256"] = sha256_json(body)
        valid, errors = validate_windows_qualification_receipt(
            receipt,
            expected_version=__version__,
        )
        self.assertFalse(valid)
        self.assertIn(
            "exact rollback not proven: windows.interface.metric",
            errors,
        )

    def test_tampered_receipt_fingerprint_is_rejected(self):
        receipt = pass_receipt()
        receipt["operator_label"] = "tampered"
        valid, errors = validate_windows_qualification_receipt(
            receipt,
            expected_version=__version__,
        )
        self.assertFalse(valid)
        self.assertIn(
            "qualification receipt fingerprint mismatch",
            errors,
        )

    def test_home_gate_recognizes_only_valid_latest_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            target = home / "qualification" / "windows-repair"
            target.mkdir(parents=True)
            (target / "latest.json").write_text(
                json.dumps(pass_receipt()),
                encoding="utf-8",
            )
            gate = qualification_gate_from_home(home)
            self.assertEqual(
                gate["status"],
                "QUALIFIED_BY_LOCAL_RECEIPT",
            )
            self.assertTrue(gate["receipt_sha256"])


if __name__ == "__main__":
    unittest.main()
