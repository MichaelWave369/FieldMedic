import json
import tempfile
import unittest
from pathlib import Path
import zipfile

from fieldmedic.external_gates import (
    ExternalGateError,
    drivemedic_lifecycle_gate_from_home,
    import_drivemedic_lifecycle,
    import_netmedic_field,
    netmedic_field_gate_from_home,
    validate_drivemedic_lifecycle_bundle,
    validate_netmedic_field_bundle,
)
from fieldmedic.hashutil import sha256_json
import hashlib


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def drive_bundle(path: Path, *, elapsed=24.0):
    validation = {
        "product": "DriveMedic",
        "version": "1.0.0-rc13",
        "phase": "phase3-final",
        "timestampUtc": "2026-10-07T00:00:00Z",
        "passed": 4,
        "failed": 0,
        "checks": [
            {"name": "Installed binary after soak", "passed": True, "detail": "ok"},
            {"name": "Recorder heartbeat after soak", "passed": True, "detail": "ok"},
            {"name": "Telemetry growth", "passed": True, "detail": "ok"},
            {"name": "Database growth sanity", "passed": True, "detail": "ok"},
        ],
        "nextState": {
            "phase": "complete",
            "version": "1.0.0-rc13",
            "completedUtc": "2026-10-07T00:00:00Z",
            "elapsedHours": elapsed,
            "snapshotGrowth": 120,
            "dailyGrowthBytes": 1024 * 1024,
        },
        "privacy": "sanitized",
    }
    payload = json.dumps(validation).encode()
    text = b"PASS\n"
    files = {
        "lifecycle-validation.json": payload,
        "lifecycle-validation.txt": text,
    }
    manifest = {
        "product": "DriveMedic",
        "version": "1.0.0-rc13",
        "phase": "phase3-final",
        "files": [
            {"path": name, "bytes": len(data), "sha256": sha(data)}
            for name, data in files.items()
        ],
    }
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
        zf.writestr("lifecycle-manifest.json", json.dumps(manifest))


def net_bundle(path: Path):
    evidence = {
        "build.txt": b"build",
        "wifi.json": b"wifi",
        "permission.txt": b"permission",
        "ethernet.json": b"ethernet",
        "vpn.json": b"vpn",
        "case.zip": b"case",
        "field-gates.txt": b"native gates",
    }
    mapping = {
        "build_runtime": "build.txt",
        "wifi_connected": "wifi.json",
        "wifi_permission": "permission.txt",
        "ethernet_ab": "ethernet.json",
        "vpn_ab": "vpn.json",
        "case_workspace": "case.zip",
    }
    gates = []
    for gate_id, rel in mapping.items():
        gates.append({
            "id": gate_id,
            "title": gate_id,
            "required": True,
            "status": "PASS",
            "evidence_complete": True,
            "notes": "",
            "evidence": [{
                "path": rel,
                "exists": True,
                "sha256": sha(evidence[rel]),
            }],
        })
    verdict = {
        "schema_version": "0.34-field",
        "app": "Parallax NetMedic",
        "version": "0.34.0",
        "captured_at_utc": "2026-10-07T00:00:00Z",
        "target_platform": "windows",
        "evaluator_platform": "windows",
        "operator": "operator",
        "verdict": "windows_field_verified",
        "scope": "operator-attested",
        "gates": gates,
    }
    evidence["field-verdict.json"] = json.dumps(verdict).encode()
    ledger = "".join(
        f"{sha(data)}  {name}\n"
        for name, data in sorted(evidence.items())
    ).encode()
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in evidence.items():
            zf.writestr(name, data)
        zf.writestr("field-hashes.sha256", ledger)


class ExternalGateTests(unittest.TestCase):
    def test_drivemedic_final_lifecycle_bundle_validates_and_imports(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bundle = root / "drive.zip"
            drive_bundle(bundle)
            result = validate_drivemedic_lifecycle_bundle(bundle)
            self.assertEqual(result["status"], "PASS")
            self.assertGreaterEqual(result["elapsed_hours"], 20.0)
            receipt = import_drivemedic_lifecycle(root / "home", bundle)
            self.assertEqual(receipt["validation"]["status"], "PASS")
            gate = drivemedic_lifecycle_gate_from_home(root / "home")
            self.assertEqual(
                gate["status"],
                "LIFECYCLE_QUALIFIED_BY_IMPORTED_NATIVE_RECEIPT",
            )

    def test_drivemedic_skip_soak_style_short_bundle_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            bundle = Path(td) / "drive-short.zip"
            drive_bundle(bundle, elapsed=1.0)
            with self.assertRaises(ExternalGateError):
                validate_drivemedic_lifecycle_bundle(bundle)

    def test_drivemedic_tampered_member_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            original = root / "drive.zip"
            drive_bundle(original)
            tampered = root / "tampered.zip"
            with zipfile.ZipFile(original, "r") as src, zipfile.ZipFile(tampered, "w") as dst:
                for info in src.infolist():
                    data = src.read(info.filename)
                    if info.filename == "lifecycle-validation.txt":
                        data += b"tamper"
                    dst.writestr(info.filename, data)
            with self.assertRaises(ExternalGateError):
                validate_drivemedic_lifecycle_bundle(tampered)

    def test_netmedic_native_field_bundle_validates_and_imports(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bundle = root / "net.zip"
            net_bundle(bundle)
            result = validate_netmedic_field_bundle(bundle)
            self.assertEqual(result["native_verdict"], "windows_field_verified")
            receipt = import_netmedic_field(root / "home", bundle)
            self.assertEqual(receipt["validation"]["status"], "PASS")
            gate = netmedic_field_gate_from_home(root / "home")
            self.assertEqual(
                gate["status"],
                "FIELD_VERIFIED_BY_IMPORTED_NATIVE_RECEIPT",
            )

    def test_netmedic_tampered_referenced_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            original = root / "net.zip"
            net_bundle(original)
            tampered = root / "tampered.zip"
            with zipfile.ZipFile(original, "r") as src, zipfile.ZipFile(tampered, "w") as dst:
                for info in src.infolist():
                    data = src.read(info.filename)
                    if info.filename == "wifi.json":
                        data += b"tamper"
                    dst.writestr(info.filename, data)
            with self.assertRaises(ExternalGateError):
                validate_netmedic_field_bundle(tampered)

    def test_netmedic_attention_verdict_is_not_promoted(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            original = root / "net.zip"
            net_bundle(original)
            modified = root / "attention.zip"
            with zipfile.ZipFile(original, "r") as src:
                all_data = {info.filename: src.read(info.filename) for info in src.infolist()}
            verdict = json.loads(all_data["field-verdict.json"])
            verdict["verdict"] = "field_validation_complete_with_attention"
            all_data["field-verdict.json"] = json.dumps(verdict).encode()
            # rebuild native hash ledger so only the semantic verdict blocks promotion
            ledger_data = {
                name: data for name, data in all_data.items()
                if name != "field-hashes.sha256"
            }
            all_data["field-hashes.sha256"] = "".join(
                f"{sha(data)}  {name}\n"
                for name, data in sorted(ledger_data.items())
            ).encode()
            with zipfile.ZipFile(modified, "w") as dst:
                for name, data in all_data.items():
                    dst.writestr(name, data)
            with self.assertRaises(ExternalGateError):
                validate_netmedic_field_bundle(modified)


if __name__ == "__main__":
    unittest.main()
