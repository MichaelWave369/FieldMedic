from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
from typing import Any
import zipfile

from .hashutil import sha256_json


class ExternalGateError(RuntimeError):
    pass


HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")
DRIVE_SCHEMA = "field-medic-drivemedic-lifecycle-import-v1"
NET_SCHEMA = "field-medic-netmedic-field-import-v1"
GIB = 1024 * 1024 * 1024


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _safe_name(name: str) -> str:
    normalized = name.replace("\\", "/")
    pure = PurePosixPath(normalized)
    if pure.is_absolute() or ".." in pure.parts or not pure.parts:
        raise ExternalGateError(f"unsafe ZIP member path: {name}")
    return pure.as_posix()


def _zip_files(zf: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    result: dict[str, zipfile.ZipInfo] = {}
    for info in zf.infolist():
        if info.is_dir():
            continue
        name = _safe_name(info.filename)
        if name in result:
            raise ExternalGateError(f"duplicate ZIP member: {name}")
        result[name] = info
    return result


def _read_json(zf: zipfile.ZipFile, name: str) -> dict[str, Any]:
    try:
        value = json.loads(zf.read(name))
    except KeyError as exc:
        raise ExternalGateError(f"missing required ZIP member: {name}") from exc
    except json.JSONDecodeError as exc:
        raise ExternalGateError(f"invalid JSON in {name}: {exc}") from exc
    if not isinstance(value, dict):
        raise ExternalGateError(f"JSON root must be an object: {name}")
    return value


def validate_drivemedic_lifecycle_bundle(bundle: Path) -> dict[str, Any]:
    if not bundle.is_file():
        raise ExternalGateError(f"DriveMedic lifecycle bundle not found: {bundle}")

    bundle_sha = _sha256_file(bundle)
    with zipfile.ZipFile(bundle, "r") as zf:
        members = _zip_files(zf)
        for required in ("lifecycle-validation.json", "lifecycle-manifest.json"):
            if required not in members:
                raise ExternalGateError(f"DriveMedic bundle missing {required}")

        manifest = _read_json(zf, "lifecycle-manifest.json")
        if manifest.get("product") != "DriveMedic":
            raise ExternalGateError("DriveMedic lifecycle manifest product mismatch")
        if manifest.get("phase") != "phase3-final":
            raise ExternalGateError(
                f"DriveMedic lifecycle bundle is not final phase3 evidence: {manifest.get('phase')}"
            )
        version = str(manifest.get("version", "")).strip()
        if not version:
            raise ExternalGateError("DriveMedic lifecycle version is missing")

        listed: dict[str, dict[str, Any]] = {}
        files = manifest.get("files")
        if not isinstance(files, list) or not files:
            raise ExternalGateError("DriveMedic lifecycle manifest files are missing")
        for item in files:
            if not isinstance(item, dict):
                raise ExternalGateError("invalid DriveMedic lifecycle manifest file record")
            rel = _safe_name(str(item.get("path", "")))
            if rel in listed:
                raise ExternalGateError(f"duplicate DriveMedic manifest path: {rel}")
            if rel == "lifecycle-manifest.json":
                raise ExternalGateError("DriveMedic manifest must not hash itself")
            listed[rel] = item

        actual = set(members) - {"lifecycle-manifest.json"}
        if set(listed) != actual:
            missing = sorted(set(listed) - actual)
            extra = sorted(actual - set(listed))
            raise ExternalGateError(
                f"DriveMedic lifecycle manifest/member mismatch; missing={missing} extra={extra}"
            )

        for rel, item in listed.items():
            data = zf.read(rel)
            if int(item.get("bytes", -1)) != len(data):
                raise ExternalGateError(f"DriveMedic lifecycle size mismatch: {rel}")
            expected = str(item.get("sha256", "")).lower()
            if not HEX64.fullmatch(expected):
                raise ExternalGateError(f"invalid DriveMedic lifecycle SHA-256: {rel}")
            if _sha256_bytes(data) != expected:
                raise ExternalGateError(f"DriveMedic lifecycle SHA-256 mismatch: {rel}")

        report = _read_json(zf, "lifecycle-validation.json")
        if report.get("product") != "DriveMedic":
            raise ExternalGateError("DriveMedic lifecycle report product mismatch")
        if str(report.get("version", "")) != version:
            raise ExternalGateError("DriveMedic lifecycle version mismatch")
        if report.get("phase") != "phase3-final":
            raise ExternalGateError("DriveMedic lifecycle report is not phase3-final")
        if int(report.get("failed", -1)) != 0:
            raise ExternalGateError("DriveMedic final lifecycle report contains failed checks")
        checks = report.get("checks")
        if not isinstance(checks, list) or not checks:
            raise ExternalGateError("DriveMedic final lifecycle checks are missing")
        if any(not isinstance(item, dict) or item.get("passed") is not True for item in checks):
            raise ExternalGateError("DriveMedic final lifecycle contains a non-passing check")
        if int(report.get("passed", -1)) != len(checks):
            raise ExternalGateError("DriveMedic lifecycle pass count does not match checks")

        state = report.get("nextState")
        if not isinstance(state, dict) or state.get("phase") != "complete":
            raise ExternalGateError("DriveMedic lifecycle did not reach complete state")
        if str(state.get("version", "")) != version:
            raise ExternalGateError("DriveMedic completed-state version mismatch")
        try:
            elapsed = float(state["elapsedHours"])
            snapshot_growth = int(state["snapshotGrowth"])
            daily_growth = float(state["dailyGrowthBytes"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ExternalGateError(
                "DriveMedic completed-state soak metrics are incomplete"
            ) from exc
        if elapsed < 20.0:
            raise ExternalGateError(
                f"DriveMedic soak is too short for release qualification: {elapsed:.2f}h"
            )
        if snapshot_growth <= 0:
            raise ExternalGateError("DriveMedic soak recorded no snapshot growth")
        if daily_growth < 0 or daily_growth >= GIB:
            raise ExternalGateError(
                "DriveMedic database growth failed the <1 GiB/day release bound"
            )

    return {
        "product": "DriveMedic",
        "version": version,
        "phase": "phase3-final",
        "bundle_sha256": bundle_sha,
        "elapsed_hours": elapsed,
        "snapshot_growth": snapshot_growth,
        "daily_growth_bytes": daily_growth,
        "check_count": len(checks),
        "status": "PASS",
        "claim_boundary": (
            "Validated DriveMedic-native sanitized phase3 lifecycle evidence and its "
            "internal hashes; this is local artifact verification, not remote attestation."
        ),
    }


def _parse_hash_ledger(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2 or not HEX64.fullmatch(parts[0]):
            raise ExternalGateError(f"invalid SHA-256 ledger line {number}")
        rel = _safe_name(parts[1].strip())
        if rel in result:
            raise ExternalGateError(f"duplicate SHA-256 ledger path: {rel}")
        result[rel] = parts[0].lower()
    return result


def validate_netmedic_field_bundle(bundle: Path) -> dict[str, Any]:
    if not bundle.is_file():
        raise ExternalGateError(f"NetMedic field bundle not found: {bundle}")

    bundle_sha = _sha256_file(bundle)
    with zipfile.ZipFile(bundle, "r") as zf:
        members = _zip_files(zf)
        required_files = {"field-verdict.json", "field-hashes.sha256", "field-gates.txt"}
        missing_required = sorted(required_files - set(members))
        if missing_required:
            raise ExternalGateError(
                f"NetMedic field bundle missing required files: {missing_required}"
            )

        ledger = _parse_hash_ledger(
            zf.read("field-hashes.sha256").decode("utf-8-sig")
        )
        actual_for_ledger = set(members) - {"field-hashes.sha256"}
        if set(ledger) != actual_for_ledger:
            missing = sorted(set(ledger) - actual_for_ledger)
            extra = sorted(actual_for_ledger - set(ledger))
            raise ExternalGateError(
                f"NetMedic field hash ledger/member mismatch; missing={missing} extra={extra}"
            )
        for rel, expected in ledger.items():
            if _sha256_bytes(zf.read(rel)) != expected:
                raise ExternalGateError(f"NetMedic field SHA-256 mismatch: {rel}")

        verdict = _read_json(zf, "field-verdict.json")
        if verdict.get("schema_version") != "0.34-field":
            raise ExternalGateError("NetMedic field schema is not 0.34-field")
        version = str(verdict.get("version", "")).strip()
        if not version.startswith("0.34"):
            raise ExternalGateError(
                f"unexpected NetMedic field version for this adapter: {version}"
            )
        if str(verdict.get("target_platform", "")).lower() != "windows":
            raise ExternalGateError("NetMedic field target platform is not Windows")
        if str(verdict.get("evaluator_platform", "")).lower() != "windows":
            raise ExternalGateError("NetMedic field evaluator did not run on Windows")
        if verdict.get("verdict") != "windows_field_verified":
            raise ExternalGateError(
                f"NetMedic native field verdict is not windows_field_verified: "
                f"{verdict.get('verdict')}"
            )

        required_ids = {
            "build_runtime",
            "wifi_connected",
            "wifi_permission",
            "ethernet_ab",
            "vpn_ab",
            "case_workspace",
        }
        gates = verdict.get("gates")
        if not isinstance(gates, list):
            raise ExternalGateError("NetMedic field gates array is missing")
        by_id: dict[str, dict[str, Any]] = {}
        for gate in gates:
            if not isinstance(gate, dict) or not gate.get("id"):
                raise ExternalGateError("invalid NetMedic field gate record")
            gate_id = str(gate["id"])
            if gate_id in by_id:
                raise ExternalGateError(f"duplicate NetMedic field gate: {gate_id}")
            by_id[gate_id] = gate

        if not required_ids.issubset(by_id):
            raise ExternalGateError(
                f"NetMedic required field gates missing: {sorted(required_ids - set(by_id))}"
            )

        evidence_count = 0
        for gate_id in sorted(required_ids):
            gate = by_id[gate_id]
            if gate.get("required") is not True:
                raise ExternalGateError(f"NetMedic required gate not marked required: {gate_id}")
            if gate.get("status") != "PASS":
                raise ExternalGateError(f"NetMedic required gate did not PASS: {gate_id}")
            if gate.get("evidence_complete") is not True:
                raise ExternalGateError(
                    f"NetMedic required gate evidence incomplete: {gate_id}"
                )
            refs = gate.get("evidence")
            if not isinstance(refs, list) or not refs:
                raise ExternalGateError(
                    f"NetMedic required gate has no evidence: {gate_id}"
                )
            for ref in refs:
                if not isinstance(ref, dict):
                    raise ExternalGateError(
                        f"invalid NetMedic evidence record for gate {gate_id}"
                    )
                rel = _safe_name(str(ref.get("path", "")))
                expected = str(ref.get("sha256", "")).lower()
                if ref.get("exists") is not True or not HEX64.fullmatch(expected):
                    raise ExternalGateError(
                        f"NetMedic evidence reference is incomplete: {gate_id}/{rel}"
                    )
                if rel not in members:
                    raise ExternalGateError(
                        f"NetMedic referenced evidence missing from ZIP: {rel}"
                    )
                if _sha256_bytes(zf.read(rel)) != expected:
                    raise ExternalGateError(
                        f"NetMedic referenced evidence hash mismatch: {rel}"
                    )
                evidence_count += 1

    return {
        "product": "NetMedic",
        "version": version,
        "native_verdict": "windows_field_verified",
        "bundle_sha256": bundle_sha,
        "required_gate_count": len(required_ids),
        "referenced_evidence_count": evidence_count,
        "status": "PASS",
        "claim_boundary": (
            "Validated NetMedic-native operator-attested field verdict and referenced "
            "evidence hashes; hashes prove artifact integrity, not operator honesty, "
            "remote attestation, identity, or scientific truth."
        ),
    }


def _import_bundle(
    *,
    home: Path,
    product_dir: str,
    schema: str,
    bundle: Path,
    validator,
) -> dict[str, Any]:
    validation = validator(bundle)
    bundle_sha = validation["bundle_sha256"]
    root = home / "qualification" / product_dir
    evidence = root / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    stored = evidence / f"{bundle_sha}.zip"
    if not stored.exists():
        shutil.copy2(bundle, stored)
    if _sha256_file(stored) != bundle_sha:
        raise ExternalGateError("stored external qualification bundle hash mismatch")

    body = {
        "schema": schema,
        "imported_at": _utc_now(),
        "source_bundle_name": bundle.name,
        "stored_bundle": str(stored.resolve()),
        "bundle_sha256": bundle_sha,
        "validation": validation,
    }
    receipt = {**body, "receipt_sha256": sha256_json(body)}
    root.mkdir(parents=True, exist_ok=True)
    (root / "latest.json").write_text(
        json.dumps(receipt, indent=2),
        encoding="utf-8",
    )
    return receipt


def import_drivemedic_lifecycle(home: Path, bundle: Path) -> dict[str, Any]:
    return _import_bundle(
        home=home,
        product_dir="drivemedic-lifecycle",
        schema=DRIVE_SCHEMA,
        bundle=bundle,
        validator=validate_drivemedic_lifecycle_bundle,
    )


def import_netmedic_field(home: Path, bundle: Path) -> dict[str, Any]:
    return _import_bundle(
        home=home,
        product_dir="netmedic-field",
        schema=NET_SCHEMA,
        bundle=bundle,
        validator=validate_netmedic_field_bundle,
    )


def _external_gate_from_home(
    *,
    home: Path,
    product_dir: str,
    schema: str,
    validator,
    qualified_status: str,
) -> dict[str, Any]:
    path = home / "qualification" / product_dir / "latest.json"
    if not path.exists():
        return {
            "status": "UNPROVEN_BY_LOCAL_RECEIPT",
            "receipt_path": None,
            "receipt_sha256": None,
            "native": None,
            "errors": ["external qualification receipt not found"],
        }
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(receipt, dict):
            raise ExternalGateError("external gate receipt root must be an object")
        if receipt.get("schema") != schema:
            raise ExternalGateError("external gate receipt schema mismatch")
        body = {
            key: value for key, value in receipt.items()
            if key != "receipt_sha256"
        }
        if receipt.get("receipt_sha256") != sha256_json(body):
            raise ExternalGateError("external gate receipt fingerprint mismatch")
        stored = Path(str(receipt.get("stored_bundle", "")))
        expected_sha = str(receipt.get("bundle_sha256", "")).lower()
        if not stored.is_file() or not HEX64.fullmatch(expected_sha):
            raise ExternalGateError("stored external qualification bundle is unavailable")
        if _sha256_file(stored) != expected_sha:
            raise ExternalGateError("stored external qualification bundle changed")
        native = validator(stored)
        if native.get("bundle_sha256") != expected_sha:
            raise ExternalGateError("native revalidation bundle hash mismatch")
    except Exception as exc:
        return {
            "status": "INVALID_LOCAL_RECEIPT",
            "receipt_path": str(path),
            "receipt_sha256": None,
            "native": None,
            "errors": [str(exc)],
        }
    return {
        "status": qualified_status,
        "receipt_path": str(path),
        "receipt_sha256": receipt.get("receipt_sha256"),
        "native": native,
        "errors": [],
    }


def drivemedic_lifecycle_gate_from_home(home: Path) -> dict[str, Any]:
    return _external_gate_from_home(
        home=home,
        product_dir="drivemedic-lifecycle",
        schema=DRIVE_SCHEMA,
        validator=validate_drivemedic_lifecycle_bundle,
        qualified_status="LIFECYCLE_QUALIFIED_BY_IMPORTED_NATIVE_RECEIPT",
    )


def netmedic_field_gate_from_home(home: Path) -> dict[str, Any]:
    return _external_gate_from_home(
        home=home,
        product_dir="netmedic-field",
        schema=NET_SCHEMA,
        validator=validate_netmedic_field_bundle,
        qualified_status="FIELD_VERIFIED_BY_IMPORTED_NATIVE_RECEIPT",
    )
