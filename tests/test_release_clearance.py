import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fieldmedic.release_clearance import build_release_clearance


DISCOVERY = {
    "schema": "field-medic-engine-discovery-v1",
    "drivemedic": {
        "present": True,
        "healthy": True,
        "version": "DriveMedic 1.0.0-rc13",
    },
    "netmedic": {
        "present": True,
        "healthy": True,
        "version": "Parallax NetMedic v0.34.0",
    },
    "ready_for_diagnostics": True,
}


def gate(status, native=None):
    return {
        "status": status,
        "receipt_path": "receipt.json",
        "receipt_sha256": "a" * 64,
        "native": native,
        "errors": [],
    }


class ReleaseClearanceTests(unittest.TestCase):
    def test_all_independent_gates_only_make_stable_packaging_eligible(self):
        with tempfile.TemporaryDirectory() as td, patch(
            "fieldmedic.release_clearance.discover_engines",
            return_value=DISCOVERY,
        ), patch(
            "fieldmedic.release_clearance.install_gate_from_home",
            return_value=gate("INSTALLED_BY_LOCAL_RECEIPT"),
        ), patch(
            "fieldmedic.release_clearance.install_smoke_gate_from_home",
            return_value=gate("QUALIFIED_BY_LOCAL_RECEIPT"),
        ), patch(
            "fieldmedic.release_clearance.qualification_gate_from_home",
            return_value=gate("QUALIFIED_BY_LOCAL_RECEIPT"),
        ), patch(
            "fieldmedic.release_clearance.drivemedic_lifecycle_gate_from_home",
            return_value=gate(
                "LIFECYCLE_QUALIFIED_BY_IMPORTED_NATIVE_RECEIPT",
                {"version": "1.0.0-rc13"},
            ),
        ), patch(
            "fieldmedic.release_clearance.netmedic_field_gate_from_home",
            return_value=gate(
                "FIELD_VERIFIED_BY_IMPORTED_NATIVE_RECEIPT",
                {"version": "0.34.0"},
            ),
        ), patch(
            "fieldmedic.release_clearance.netmedic_license_gate_from_home",
            return_value=gate(
                "PUBLIC_MIT_LICENSE_VERIFIED_BY_SOURCE_HANDOFF",
                {"version": "0.34.0"},
            ),
        ):
            result = build_release_clearance(home=Path(td))
        self.assertEqual(
            result["status"],
            "ELIGIBLE_FOR_STABLE_PACKAGING",
        )
        self.assertFalse(result["stable_release_claim"])
        self.assertEqual(
            result["next_gate"],
            "BUILD_FINAL_STABLE_PACKAGE_AND_HASH_RECEIPT",
        )

    def test_missing_gate_remains_incomplete(self):
        with tempfile.TemporaryDirectory() as td, patch(
            "fieldmedic.release_clearance.discover_engines",
            return_value=DISCOVERY,
        ), patch(
            "fieldmedic.release_clearance.install_gate_from_home",
            return_value=gate("INSTALLED_BY_LOCAL_RECEIPT"),
        ), patch(
            "fieldmedic.release_clearance.install_smoke_gate_from_home",
            return_value=gate("UNPROVEN_BY_LOCAL_RECEIPT"),
        ), patch(
            "fieldmedic.release_clearance.qualification_gate_from_home",
            return_value=gate("QUALIFIED_BY_LOCAL_RECEIPT"),
        ), patch(
            "fieldmedic.release_clearance.drivemedic_lifecycle_gate_from_home",
            return_value=gate(
                "LIFECYCLE_QUALIFIED_BY_IMPORTED_NATIVE_RECEIPT",
                {"version": "1.0.0-rc13"},
            ),
        ), patch(
            "fieldmedic.release_clearance.netmedic_field_gate_from_home",
            return_value=gate(
                "FIELD_VERIFIED_BY_IMPORTED_NATIVE_RECEIPT",
                {"version": "0.34.0"},
            ),
        ), patch(
            "fieldmedic.release_clearance.netmedic_license_gate_from_home",
            return_value=gate(
                "PUBLIC_MIT_LICENSE_VERIFIED_BY_SOURCE_HANDOFF",
                {"version": "0.34.0"},
            ),
        ):
            result = build_release_clearance(home=Path(td))
        self.assertEqual(result["status"], "RELEASE_CLEARANCE_INCOMPLETE")

    def test_invalid_evidence_blocks_clearance(self):
        with tempfile.TemporaryDirectory() as td, patch(
            "fieldmedic.release_clearance.discover_engines",
            return_value=DISCOVERY,
        ), patch(
            "fieldmedic.release_clearance.install_gate_from_home",
            return_value=gate("INVALID_LOCAL_RECEIPT"),
        ), patch(
            "fieldmedic.release_clearance.install_smoke_gate_from_home",
            return_value=gate("QUALIFIED_BY_LOCAL_RECEIPT"),
        ), patch(
            "fieldmedic.release_clearance.qualification_gate_from_home",
            return_value=gate("QUALIFIED_BY_LOCAL_RECEIPT"),
        ), patch(
            "fieldmedic.release_clearance.drivemedic_lifecycle_gate_from_home",
            return_value=gate(
                "LIFECYCLE_QUALIFIED_BY_IMPORTED_NATIVE_RECEIPT",
                {"version": "1.0.0-rc13"},
            ),
        ), patch(
            "fieldmedic.release_clearance.netmedic_field_gate_from_home",
            return_value=gate(
                "FIELD_VERIFIED_BY_IMPORTED_NATIVE_RECEIPT",
                {"version": "0.34.0"},
            ),
        ), patch(
            "fieldmedic.release_clearance.netmedic_license_gate_from_home",
            return_value=gate(
                "PUBLIC_MIT_LICENSE_VERIFIED_BY_SOURCE_HANDOFF",
                {"version": "0.34.0"},
            ),
        ):
            result = build_release_clearance(home=Path(td))
        self.assertEqual(result["status"], "BLOCKED_INVALID_EVIDENCE")

    def test_native_version_mismatch_prevents_packaging_eligibility(self):
        bad = dict(DISCOVERY)
        bad["drivemedic"] = dict(DISCOVERY["drivemedic"])
        bad["drivemedic"]["version"] = "DriveMedic 9.9.9"
        with tempfile.TemporaryDirectory() as td, patch(
            "fieldmedic.release_clearance.discover_engines",
            return_value=bad,
        ), patch(
            "fieldmedic.release_clearance.install_gate_from_home",
            return_value=gate("INSTALLED_BY_LOCAL_RECEIPT"),
        ), patch(
            "fieldmedic.release_clearance.install_smoke_gate_from_home",
            return_value=gate("QUALIFIED_BY_LOCAL_RECEIPT"),
        ), patch(
            "fieldmedic.release_clearance.qualification_gate_from_home",
            return_value=gate("QUALIFIED_BY_LOCAL_RECEIPT"),
        ), patch(
            "fieldmedic.release_clearance.drivemedic_lifecycle_gate_from_home",
            return_value=gate(
                "LIFECYCLE_QUALIFIED_BY_IMPORTED_NATIVE_RECEIPT",
                {"version": "1.0.0-rc13"},
            ),
        ), patch(
            "fieldmedic.release_clearance.netmedic_field_gate_from_home",
            return_value=gate(
                "FIELD_VERIFIED_BY_IMPORTED_NATIVE_RECEIPT",
                {"version": "0.34.0"},
            ),
        ), patch(
            "fieldmedic.release_clearance.netmedic_license_gate_from_home",
            return_value=gate(
                "PUBLIC_MIT_LICENSE_VERIFIED_BY_SOURCE_HANDOFF",
                {"version": "0.34.0"},
            ),
        ):
            result = build_release_clearance(home=Path(td))
        self.assertEqual(result["status"], "RELEASE_CLEARANCE_INCOMPLETE")
        self.assertFalse(result["checks"]["drivemedic_version_alignment"])


if __name__ == "__main__":
    unittest.main()
