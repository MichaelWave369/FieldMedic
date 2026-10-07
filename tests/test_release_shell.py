import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fieldmedic.dashboard import (
    build_dashboard_model,
    render_dashboard,
)
from fieldmedic.release_receipt import build_release_receipt


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


class ReleaseShellTests(unittest.TestCase):
    def test_release_receipt_does_not_claim_unproven_live_gates(self):
        with tempfile.TemporaryDirectory() as td, patch(
            "fieldmedic.release_receipt.discover_engines",
            return_value=DISCOVERY,
        ):
            receipt = build_release_receipt(home=Path(td))
        self.assertEqual(
            receipt["release_gates"]["live_windows_repair_executors_qualified"],
            "UNPROVEN_BY_LOCAL_RECEIPT",
        )
        self.assertEqual(
            receipt["release_gates"]["drivemedic_lifecycle_qualified"],
            "UNPROVEN_BY_LOCAL_RECEIPT",
        )
        self.assertIn("receipt_sha256", receipt)

    def test_dashboard_is_one_read_only_operator_surface(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            case = home / "cases" / "case-1"
            case.mkdir(parents=True)
            (case / "case.json").write_text(
                json.dumps({
                    "case_id": "case-1",
                    "symptom": "<script>alert(1)</script>",
                    "routing": {"domain": "mixed"},
                    "errors": [],
                }),
                encoding="utf-8",
            )
            with patch(
                "fieldmedic.dashboard.discover_engines",
                return_value=DISCOVERY,
            ), patch(
                "fieldmedic.release_receipt.discover_engines",
                return_value=DISCOVERY,
            ):
                model = build_dashboard_model(home=home)
            html = render_dashboard(model)
            self.assertIn("Field Medic", html)
            self.assertIn("case-1", html)
            self.assertNotIn("<script>alert(1)</script>", html)
            self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
            self.assertIn(
                "This file is a read-only snapshot; it grants no authority.",
                html,
            )


if __name__ == "__main__":
    unittest.main()
