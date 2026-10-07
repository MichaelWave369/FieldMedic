from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
from typing import Any

from . import __version__
from .hashutil import sha256_json


SMOKE_SCHEMA = "field-medic-windows-install-smoke-v1"


class InstallSmokeError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_install_smoke_receipt(
    *,
    output: Path,
    bundle: Path,
    install_root: Path,
    data_root: Path,
    install_receipt_sha256: str,
    discover_pass: bool,
    dashboard_pass: bool,
    release_receipt_pass: bool,
    default_uninstall_pass: bool,
    data_preserved: bool,
    sentinel_preserved: bool,
) -> dict[str, Any]:
    if os.name != "nt":
        raise InstallSmokeError("Windows install smoke receipt must be produced on Windows")
    if not bundle.is_file():
        raise InstallSmokeError(f"bundle not found: {bundle}")

    checks = {
        "install_completed": bool(install_receipt_sha256),
        "discover_pass": bool(discover_pass),
        "dashboard_pass": bool(dashboard_pass),
        "release_receipt_pass": bool(release_receipt_pass),
        "default_uninstall_pass": bool(default_uninstall_pass),
        "data_preserved": bool(data_preserved),
        "sentinel_preserved": bool(sentinel_preserved),
        "program_removed": not install_root.exists(),
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    body = {
        "schema": SMOKE_SCHEMA,
        "fieldmedic_version": __version__,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": status,
        "platform": {
            "os_name": os.name,
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "bundle": {
            "path": str(bundle.resolve()),
            "size_bytes": bundle.stat().st_size,
            "sha256": _sha256(bundle),
        },
        "install_root": str(install_root),
        "data_root": str(data_root),
        "install_receipt_sha256": install_receipt_sha256,
        "checks": checks,
        "claim_boundary": (
            "PASS proves this bundle completed one per-user install / product smoke / "
            "default uninstall cycle on the recorded Windows environment and preserved "
            "the designated data root. It is not a universal Windows compatibility claim."
        ),
    }
    receipt = {**body, "receipt_sha256": sha256_json(body)}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt


def validate_install_smoke_receipt(
    receipt: dict[str, Any],
    *,
    expected_version: str | None = None,
) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if receipt.get("schema") != SMOKE_SCHEMA:
        errors.append("unexpected install smoke schema")
    body = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    if receipt.get("receipt_sha256") != sha256_json(body):
        errors.append("install smoke receipt fingerprint mismatch")
    if receipt.get("status") != "PASS":
        errors.append("install smoke status is not PASS")
    if expected_version and receipt.get("fieldmedic_version") != expected_version:
        errors.append("install smoke FieldMedic version mismatch")
    if receipt.get("platform", {}).get("os_name") != "nt":
        errors.append("install smoke was not produced on Windows")
    checks = receipt.get("checks")
    if not isinstance(checks, dict):
        errors.append("install smoke checks missing")
    else:
        for key in (
            "install_completed",
            "discover_pass",
            "dashboard_pass",
            "release_receipt_pass",
            "default_uninstall_pass",
            "data_preserved",
            "sentinel_preserved",
            "program_removed",
        ):
            if checks.get(key) is not True:
                errors.append(f"install smoke check failed: {key}")
    if not receipt.get("install_receipt_sha256"):
        errors.append("install smoke does not reference the install receipt")
    return not errors, errors


def install_smoke_gate_from_home(home: Path) -> dict[str, Any]:
    path = home / "qualification" / "windows-install-smoke" / "latest.json"
    if not path.exists():
        return {
            "status": "UNPROVEN_BY_LOCAL_RECEIPT",
            "receipt_path": None,
            "receipt_sha256": None,
            "errors": ["install smoke receipt not found"],
        }
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("install smoke receipt root must be an object")
        valid, errors = validate_install_smoke_receipt(
            value,
            expected_version=__version__,
        )
    except Exception as exc:
        return {
            "status": "INVALID_LOCAL_RECEIPT",
            "receipt_path": str(path),
            "receipt_sha256": None,
            "errors": [str(exc)],
        }
    return {
        "status": (
            "QUALIFIED_BY_LOCAL_RECEIPT"
            if valid
            else "INVALID_LOCAL_RECEIPT"
        ),
        "receipt_path": str(path),
        "receipt_sha256": value.get("receipt_sha256"),
        "errors": errors,
    }
