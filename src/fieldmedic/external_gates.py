from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

from .discovery import discover_engines
from .hashutil import sha256_json


EXTERNAL_GATE_SCHEMA = "field-medic-external-gate-v1"

GATE_SPECS: dict[str, dict[str, str]] = {
    "drivemedic-lifecycle": {
        "engine": "drivemedic",
        "claim": "DriveMedic lifecycle qualification completed",
    },
    "netmedic-field": {
        "engine": "netmedic",
        "claim": "NetMedic Windows/field promotion completed",
    },
    "netmedic-license": {
        "engine": "netmedic",
        "claim": "NetMedic public redistribution license aligned",
    },
}

LICENSE_MARKERS = {
    "MIT": ("permission is hereby granted, free of charge",),
    "Apache-2.0": ("apache license", "version 2.0"),
    "BSD-2-Clause": ("redistribution and use in source and binary forms",),
    "BSD-3-Clause": ("redistribution and use in source and binary forms",),
    "GPL-2.0-only": ("gnu general public license", "version 2"),
    "GPL-2.0-or-later": ("gnu general public license", "version 2"),
    "GPL-3.0-only": ("gnu general public license", "version 3"),
    "GPL-3.0-or-later": ("gnu general public license", "version 3"),
    "LGPL-2.1-only": ("gnu lesser general public license",),
    "LGPL-2.1-or-later": ("gnu lesser general public license",),
    "LGPL-3.0-only": ("gnu lesser general public license",),
    "LGPL-3.0-or-later": ("gnu lesser general public license",),
    "MPL-2.0": ("mozilla public license", "2.0"),
}

OPEN_LICENSE_IDS = {
    "MIT",
    "Apache-2.0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "GPL-2.0-only",
    "GPL-2.0-or-later",
    "GPL-3.0-only",
    "GPL-3.0-or-later",
    "LGPL-2.1-only",
    "LGPL-2.1-or-later",
    "LGPL-3.0-only",
    "LGPL-3.0-or-later",
    "MPL-2.0",
}


class ExternalGateError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _gate_root(home: Path, kind: str) -> Path:
    return home / "qualification" / "external" / kind


def import_external_gate(
    *,
    home: Path,
    kind: str,
    source_receipt: Path,
    operator_label: str,
    declared_pass: bool,
    license_id: str | None = None,
    redistribution_allowed: bool | None = None,
) -> dict[str, Any]:
    if kind not in GATE_SPECS:
        raise ExternalGateError(f"unknown external gate kind: {kind}")
    if not source_receipt.is_file():
        raise ExternalGateError(f"source receipt not found: {source_receipt}")
    if not operator_label.strip():
        raise ExternalGateError("operator label is required")
    if not declared_pass:
        raise ExternalGateError(
            "external gate import requires an explicit PASS declaration; "
            "non-passing evidence should not promote a release gate"
        )

    spec = GATE_SPECS[kind]
    discovery = discover_engines(home=home)
    engine = spec["engine"]
    observed = discovery.get(engine, {})
    version = observed.get("version")
    if observed.get("present") is not True or not version:
        raise ExternalGateError(
            f"{engine} must be discovered with a version before importing {kind}"
        )

    if kind == "netmedic-license":
        if license_id not in OPEN_LICENSE_IDS:
            raise ExternalGateError(
                "NetMedic license evidence must declare a recognized open-source SPDX ID"
            )
        if redistribution_allowed is not True:
            raise ExternalGateError(
                "NetMedic license evidence must explicitly allow redistribution"
            )
        license_text = source_receipt.read_text(
            encoding="utf-8",
            errors="replace",
        ).lower()
        markers = LICENSE_MARKERS.get(str(license_id), ())
        if not markers or not all(marker in license_text for marker in markers):
            raise ExternalGateError(
                "imported NetMedic license text does not match the declared SPDX family"
            )

    digest = _sha256(source_receipt)
    root = _gate_root(home, kind)
    artifacts = root / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    copied = artifacts / f"{digest}{source_receipt.suffix or '.bin'}"
    if not copied.exists():
        shutil.copyfile(source_receipt, copied)
    if _sha256(copied) != digest:
        raise ExternalGateError("copied external artifact hash mismatch")

    body = {
        "schema": EXTERNAL_GATE_SCHEMA,
        "kind": kind,
        "engine": engine,
        "engine_version": str(version),
        "claim": spec["claim"],
        "declared_status": "PASS",
        "operator_label": operator_label,
        "operator_label_semantics": (
            "local operator attestation; FieldMedic preserves the imported artifact "
            "and hash but does not independently certify the external qualification"
        ),
        "imported_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_artifact": {
            "original_name": source_receipt.name,
            "stored_path": str(copied),
            "size_bytes": copied.stat().st_size,
            "sha256": digest,
        },
        "license": (
            {
                "spdx_id": license_id,
                "redistribution_allowed": True,
            }
            if kind == "netmedic-license"
            else None
        ),
        "claim_boundary": (
            "This record proves which bytes were imported and what the local operator "
            "declared about them. It does not turn an external report into an "
            "independent FieldMedic measurement."
        ),
    }
    record = {**body, "record_sha256": sha256_json(body)}
    latest = root / "latest.json"
    latest.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def validate_external_gate(
    record: dict[str, Any],
    *,
    kind: str,
    expected_engine_version: str | None,
) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if kind not in GATE_SPECS:
        return False, [f"unknown external gate kind: {kind}"]
    if record.get("schema") != EXTERNAL_GATE_SCHEMA:
        errors.append("unexpected external gate schema")
    if record.get("kind") != kind:
        errors.append("external gate kind mismatch")
    body = {key: value for key, value in record.items() if key != "record_sha256"}
    if record.get("record_sha256") != sha256_json(body):
        errors.append("external gate record fingerprint mismatch")
    if record.get("declared_status") != "PASS":
        errors.append("external gate declaration is not PASS")
    if expected_engine_version and record.get("engine_version") != expected_engine_version:
        errors.append("external gate engine version mismatch")

    artifact = record.get("source_artifact", {})
    raw_path = artifact.get("stored_path")
    if not raw_path:
        errors.append("external gate artifact path missing")
    else:
        path = Path(str(raw_path))
        if not path.is_file():
            errors.append("external gate artifact copy missing")
        else:
            if path.stat().st_size != int(artifact.get("size_bytes", -1)):
                errors.append("external gate artifact size mismatch")
            if _sha256(path) != artifact.get("sha256"):
                errors.append("external gate artifact SHA-256 mismatch")

    if kind == "netmedic-license":
        license_info = record.get("license")
        if not isinstance(license_info, dict):
            errors.append("NetMedic license declaration missing")
        else:
            if license_info.get("spdx_id") not in OPEN_LICENSE_IDS:
                errors.append("NetMedic license is not in the accepted open-source set")
            if license_info.get("redistribution_allowed") is not True:
                errors.append("NetMedic redistribution permission not declared")

    return not errors, errors


def external_gate_from_home(
    *,
    home: Path,
    kind: str,
    expected_engine_version: str | None,
) -> dict[str, Any]:
    if not expected_engine_version:
        return {
            "status": "UNPROVEN_BY_LOCAL_RECEIPT",
            "record_path": None,
            "record_sha256": None,
            "errors": ["current engine version is unavailable"],
        }
    latest = _gate_root(home, kind) / "latest.json"
    if not latest.exists():
        return {
            "status": "UNPROVEN_BY_LOCAL_RECEIPT",
            "record_path": None,
            "record_sha256": None,
            "errors": ["external gate record not found"],
        }
    try:
        record = json.loads(latest.read_text(encoding="utf-8"))
        if not isinstance(record, dict):
            raise ValueError("external gate record root must be an object")
        valid, errors = validate_external_gate(
            record,
            kind=kind,
            expected_engine_version=expected_engine_version,
        )
    except Exception as exc:
        return {
            "status": "INVALID_LOCAL_RECEIPT",
            "record_path": str(latest),
            "record_sha256": None,
            "errors": [str(exc)],
        }
    return {
        "status": (
            "QUALIFIED_BY_IMPORTED_EVIDENCE"
            if valid
            else "INVALID_LOCAL_RECEIPT"
        ),
        "record_path": str(latest),
        "record_sha256": record.get("record_sha256"),
        "source_artifact_sha256": record.get("source_artifact", {}).get("sha256"),
        "errors": errors,
    }
