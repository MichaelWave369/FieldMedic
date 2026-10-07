from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
from typing import Any

from .hashutil import sha256_json


LICENSE_SCHEMA = "field-medic-netmedic-license-import-v1"


class LicenseGateError(RuntimeError):
    pass


MIT_REQUIRED = (
    "Permission is hereby granted, free of charge, to any person obtaining a copy",
    "to deal in the Software without restriction",
    "The above copyright notice and this permission notice shall be included",
    "THE SOFTWARE IS PROVIDED "AS IS"",
)

RESTRICTIVE_MARKERS = (
    "all rights reserved",
    "not licensed for redistribution",
    "private development snapshot",
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def validate_netmedic_mit_source(source_root: Path) -> dict[str, Any]:
    root = source_root.resolve()
    license_path = root / "LICENSE"
    version_path = root / "src" / "core" / "AppVersion.h"
    if not license_path.is_file():
        raise LicenseGateError(f"NetMedic LICENSE not found: {license_path}")
    if not version_path.is_file():
        raise LicenseGateError(f"NetMedic AppVersion.h not found: {version_path}")

    license_text = license_path.read_text(encoding="utf-8")
    lower = license_text.lower()
    for marker in RESTRICTIVE_MARKERS:
        if marker in lower:
            raise LicenseGateError(
                f"NetMedic source is still carrying restrictive license text: {marker}"
            )
    for clause in MIT_REQUIRED:
        if clause.lower() not in lower:
            raise LicenseGateError(
                f"NetMedic LICENSE does not contain required MIT clause: {clause}"
            )

    header = version_path.read_text(encoding="utf-8")
    version_match = re.search(
        r'#define\s+NETMEDIC_VERSION\s+"([^"]+)"',
        header,
    )
    name_match = re.search(
        r'#define\s+NETMEDIC_NAME\s+"([^"]+)"',
        header,
    )
    if not version_match or not name_match:
        raise LicenseGateError("NetMedic version/name macros not found")
    version = version_match.group(1)
    name = name_match.group(1)
    if name != "Parallax NetMedic":
        raise LicenseGateError(f"unexpected NetMedic product name: {name}")

    return {
        "product": name,
        "version": version,
        "license_spdx": "MIT",
        "license_sha256": _sha256(license_path),
        "version_header_sha256": _sha256(version_path),
        "status": "PASS",
        "claim_boundary": (
            "Validated the declared license text and product/version header in the "
            "provided NetMedic source snapshot. This is not legal advice and does not "
            "audit third-party dependency licenses or ownership."
        ),
    }


def import_netmedic_mit_license(
    home: Path,
    source_root: Path,
) -> dict[str, Any]:
    validation = validate_netmedic_mit_source(source_root)
    root = home / "qualification" / "netmedic-license"
    evidence = root / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)

    source_license = source_root.resolve() / "LICENSE"
    source_version = source_root.resolve() / "src" / "core" / "AppVersion.h"
    stored_license = evidence / "LICENSE"
    stored_version = evidence / "AppVersion.h"
    shutil.copy2(source_license, stored_license)
    shutil.copy2(source_version, stored_version)

    body = {
        "schema": LICENSE_SCHEMA,
        "imported_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "validation": validation,
        "stored_license": str(stored_license.resolve()),
        "stored_version_header": str(stored_version.resolve()),
    }
    receipt = {**body, "receipt_sha256": sha256_json(body)}
    (root / "latest.json").write_text(
        json.dumps(receipt, indent=2),
        encoding="utf-8",
    )
    return receipt


def netmedic_license_gate_from_home(home: Path) -> dict[str, Any]:
    path = home / "qualification" / "netmedic-license" / "latest.json"
    if not path.exists():
        return {
            "status": "UNPROVEN_BY_LOCAL_RECEIPT",
            "receipt_path": None,
            "receipt_sha256": None,
            "native": None,
            "errors": ["NetMedic public-license receipt not found"],
        }
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(receipt, dict):
            raise LicenseGateError("license receipt root must be an object")
        if receipt.get("schema") != LICENSE_SCHEMA:
            raise LicenseGateError("license receipt schema mismatch")
        body = {
            key: value for key, value in receipt.items()
            if key != "receipt_sha256"
        }
        if receipt.get("receipt_sha256") != sha256_json(body):
            raise LicenseGateError("license receipt fingerprint mismatch")

        stored_license = Path(str(receipt.get("stored_license", "")))
        stored_version = Path(str(receipt.get("stored_version_header", "")))
        expected = receipt.get("validation", {})
        if not stored_license.is_file() or not stored_version.is_file():
            raise LicenseGateError("stored license evidence is missing")
        if _sha256(stored_license) != expected.get("license_sha256"):
            raise LicenseGateError("stored NetMedic LICENSE changed")
        if _sha256(stored_version) != expected.get("version_header_sha256"):
            raise LicenseGateError("stored NetMedic version header changed")
        text = stored_license.read_text(encoding="utf-8").lower()
        for marker in RESTRICTIVE_MARKERS:
            if marker in text:
                raise LicenseGateError(
                    f"stored NetMedic license is restrictive: {marker}"
                )
        for clause in MIT_REQUIRED:
            if clause.lower() not in text:
                raise LicenseGateError("stored NetMedic license no longer matches MIT")
    except Exception as exc:
        return {
            "status": "INVALID_LOCAL_RECEIPT",
            "receipt_path": str(path),
            "receipt_sha256": None,
            "native": None,
            "errors": [str(exc)],
        }

    return {
        "status": "PUBLIC_MIT_LICENSE_VERIFIED_BY_SOURCE_HANDOFF",
        "receipt_path": str(path),
        "receipt_sha256": receipt.get("receipt_sha256"),
        "native": receipt.get("validation"),
        "errors": [],
    }
