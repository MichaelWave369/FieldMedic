import json
import tempfile
import unittest
from pathlib import Path
import zipfile

from fieldmedic.case_portable import (
    CaseBundleError,
    export_case,
    import_case,
)


class CasePortableTests(unittest.TestCase):
    def _case(self, root: Path, case_id: str = "case-1") -> Path:
        case = root / case_id
        case.mkdir(parents=True)
        (case / "case.json").write_text(
            json.dumps({
                "schema": "field-medic-case-v1",
                "case_id": case_id,
                "symptom": "wifi drops",
            }),
            encoding="utf-8",
        )
        (case / "evidence.jsonl").write_text(
            '{"evidence_id":"ev-1"}\n',
            encoding="utf-8",
        )
        nested = case / "repairs" / "repair-1"
        nested.mkdir(parents=True)
        (nested / "execution.json").write_text(
            '{"status":"EXECUTED_PENDING_OUTCOME_VERIFICATION"}',
            encoding="utf-8",
        )
        return case

    def test_round_trip_preserves_bytes_and_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = self._case(root / "source")
            bundle = root / "case.fieldmedic.zip"
            exported = export_case(source, bundle)
            imported = import_case(bundle, root / "destination")
            self.assertEqual(exported["case_id"], "case-1")
            self.assertEqual(
                exported["manifest_sha256"],
                imported["manifest_sha256"],
            )
            restored = root / "destination" / "case-1"
            self.assertEqual(
                (restored / "evidence.jsonl").read_bytes(),
                (source / "evidence.jsonl").read_bytes(),
            )

    def test_nonportable_case_id_is_rejected_before_export(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            case = root / "source" / "bad"
            case.mkdir(parents=True)
            (case / "case.json").write_text(
                json.dumps({"case_id": "bad:windows:id"}),
                encoding="utf-8",
            )
            with self.assertRaises(CaseBundleError):
                export_case(case, root / "bad.zip")

    def test_import_never_overwrites_existing_case(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = self._case(root / "source")
            bundle = root / "case.zip"
            export_case(source, bundle)
            existing = root / "destination" / "case-1"
            existing.mkdir(parents=True)
            with self.assertRaises(CaseBundleError):
                import_case(bundle, root / "destination")

    def test_tampered_payload_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = self._case(root / "source")
            bundle = root / "case.zip"
            export_case(source, bundle)

            tampered = root / "tampered.zip"
            with zipfile.ZipFile(bundle, "r") as src, zipfile.ZipFile(
                tampered, "w"
            ) as dst:
                for info in src.infolist():
                    data = src.read(info.filename)
                    if info.filename == "case/evidence.jsonl":
                        data += b"tamper\n"
                    dst.writestr(info, data)
            with self.assertRaises(CaseBundleError):
                import_case(tampered, root / "destination")

    def test_path_traversal_member_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bundle = root / "bad.zip"
            with zipfile.ZipFile(bundle, "w") as zf:
                zf.writestr("manifest.json", "{}")
                zf.writestr("../escape.txt", "nope")
            with self.assertRaises(CaseBundleError):
                import_case(bundle, root / "destination")


if __name__ == "__main__":
    unittest.main()
