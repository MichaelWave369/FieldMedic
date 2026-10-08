import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fieldmedic.external_gates import (
    ExternalGateError,
    import_external_gate,
    validate_external_gate,
)


DISCOVERY = {
    "drivemedic": {
        "present": True,
        "version": "DriveMedic 1.0.0-rc13",
    },
    "netmedic": {
        "present": True,
        "version": "Parallax NetMedic v0.34.0",
    },
}


class ExternalGateTests(unittest.TestCase):
    def test_import_preserves_exact_artifact_and_binds_engine_version(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "drive-receipt.json"
            source.write_text('{"status":"PASS"}', encoding="utf-8")
            with patch(
                "fieldmedic.external_gates.discover_engines",
                return_value=DISCOVERY,
            ):
                record = import_external_gate(
                    home=root / "home",
                    kind="drivemedic-lifecycle",
                    source_receipt=source,
                    operator_label="operator",
                    declared_pass=True,
                )
            valid, errors = validate_external_gate(
                record,
                kind="drivemedic-lifecycle",
                expected_engine_version="DriveMedic 1.0.0-rc13",
            )
            self.assertTrue(valid)
            self.assertEqual(errors, [])
            copied = Path(record["source_artifact"]["stored_path"])
            self.assertEqual(copied.read_bytes(), source.read_bytes())

    def test_engine_version_change_invalidates_import(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "net-receipt.txt"
            source.write_text("PASS", encoding="utf-8")
            with patch(
                "fieldmedic.external_gates.discover_engines",
                return_value=DISCOVERY,
            ):
                record = import_external_gate(
                    home=root / "home",
                    kind="netmedic-field",
                    source_receipt=source,
                    operator_label="operator",
                    declared_pass=True,
                )
            valid, errors = validate_external_gate(
                record,
                kind="netmedic-field",
                expected_engine_version="Parallax NetMedic v0.35.0",
            )
            self.assertFalse(valid)
            self.assertIn("external gate engine version mismatch", errors)

    def test_license_gate_requires_open_license_and_redistribution(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            license_file = root / "LICENSE"
            license_file.write_text("All rights reserved.", encoding="utf-8")
            with patch(
                "fieldmedic.external_gates.discover_engines",
                return_value=DISCOVERY,
            ):
                with self.assertRaises(ExternalGateError):
                    import_external_gate(
                        home=root / "home",
                        kind="netmedic-license",
                        source_receipt=license_file,
                        operator_label="operator",
                        declared_pass=True,
                        license_id="MIT",
                        redistribution_allowed=True,
                    )

    def test_matching_mit_license_artifact_is_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            license_file = root / "LICENSE"
            license_file.write_text(
                "MIT License\nPermission is hereby granted, free of charge, to any person.",
                encoding="utf-8",
            )
            with patch(
                "fieldmedic.external_gates.discover_engines",
                return_value=DISCOVERY,
            ):
                record = import_external_gate(
                    home=root / "home",
                    kind="netmedic-license",
                    source_receipt=license_file,
                    operator_label="operator",
                    declared_pass=True,
                    license_id="MIT",
                    redistribution_allowed=True,
                )
            valid, errors = validate_external_gate(
                record,
                kind="netmedic-license",
                expected_engine_version="Parallax NetMedic v0.34.0",
            )
            self.assertTrue(valid)
            self.assertEqual(errors, [])

    def test_external_artifact_tamper_invalidates_gate(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "receipt.txt"
            source.write_text("PASS", encoding="utf-8")
            with patch(
                "fieldmedic.external_gates.discover_engines",
                return_value=DISCOVERY,
            ):
                record = import_external_gate(
                    home=root / "home",
                    kind="netmedic-field",
                    source_receipt=source,
                    operator_label="operator",
                    declared_pass=True,
                )
            Path(record["source_artifact"]["stored_path"]).write_text(
                "tampered",
                encoding="utf-8",
            )
            valid, errors = validate_external_gate(
                record,
                kind="netmedic-field",
                expected_engine_version="Parallax NetMedic v0.34.0",
            )
            self.assertFalse(valid)
            self.assertIn("external gate artifact SHA-256 mismatch", errors)


if __name__ == "__main__":
    unittest.main()
