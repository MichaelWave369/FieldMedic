import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fieldmedic import __version__
from fieldmedic.hashutil import sha256_json
from fieldmedic.release_receipt import build_release_receipt
from fieldmedic.windows_qualification import QUALIFICATION_SCHEMA


DISCOVERY = {
    "schema": "field-medic-engine-discovery-v1",
    "drivemedic": {
        "engine": "drivemedic",
        "path": "C:/DriveMedic/drivemedic.exe",
        "discovered_by": "test",
        "present": True,
        "version": "DriveMedic 1.0.0-rc13",
        "healthy": True,
        "details": {},
        "errors": [],
    },
    "netmedic": {
        "engine": "netmedic",
        "path": "C:/NetMedic/netmedic.exe",
        "discovered_by": "test",
        "present": True,
        "version": "Parallax NetMedic v0.34.0",
        "healthy": True,
        "details": {},
        "errors": [],
    },
    "ready_for_diagnostics": True,
}


def receipt():
    body = {
        "schema": QUALIFICATION_SCHEMA,
        "qualification_id": "winqual-release-test",
        "fieldmedic_version": __version__,
        "generated_at": "2026-10-07T21:00:00Z",
        "status": "PASS",
        "case_id": "case-winqual-release-test",
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
            key: {
                "status": "PASS",
                "rollback_exact": True,
                "verification_status": "MEASURED_PENDING_OPERATOR_OUTCOME",
                "execution_evidence_id": f"ev-exec-{key}",
                "verification_evidence_id": f"ev-verify-{key}",
                "rollback_evidence_id": f"ev-rollback-{key}",
            }
            for key in (
                "windows.process.priority",
                "windows.interface.metric",
            )
        },
        "errors": [],
        "claim_boundary": "bounded test",
    }
    return {**body, "receipt_sha256": sha256_json(body)}


class ReleaseQualificationGateTests(unittest.TestCase):
    def test_release_receipt_can_admit_live_windows_gate_from_current_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            root = home / "qualification" / "windows-repair"
            root.mkdir(parents=True)
            (root / "latest.json").write_text(
                json.dumps(receipt()),
                encoding="utf-8",
            )
            with patch(
                "fieldmedic.release_receipt.discover_engines",
                return_value=DISCOVERY,
            ):
                result = build_release_receipt(home=home)
        self.assertEqual(
            result["release_gates"][
                "live_windows_repair_executors_qualified"
            ],
            "QUALIFIED_BY_LOCAL_RECEIPT",
        )
        self.assertEqual(
            result["qualification_receipts"][
                "windows_repair"
            ]["status"],
            "QUALIFIED_BY_LOCAL_RECEIPT",
        )


if __name__ == "__main__":
    unittest.main()
