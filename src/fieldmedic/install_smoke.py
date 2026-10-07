from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
from typing import Any

from . import __version__
from .hashutil import sha256_json
from .installation import validate_install_receipt


SMOKE_SCHEMA = "field-medic-windows-install-smoke-v1"


class InstallSmokeError(RuntimeError):
    pass


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise InstallSmokeError(f"JSON root must be an object: {path}")
    return value


def build_install_smoke_receipt(
    *,
    first_install_receipt: Path,
    second_install_receipt: Path,
    observation: Path,
) -> dict[str, Any]:
    first = _load_object(first_install_receipt)
    second = _load_object(second_install_receipt)
    observed = _load_object(observation)

    for label, receipt in (("first", first), ("second", second)):
        valid, errors = validate_install_receipt(
            receipt,
            expected_version=__version__,
        )
        if not valid:
            raise InstallSmokeError(
                f"{label} installation receipt is invalid: {errors}"
            )
        if receipt.get("engine_discovery", {}).get("ready_for_diagnostics") is not True:
            raise InstallSmokeError(
                f"{label} installation did not prove DriveMedic + NetMedic discovery"
            )

    required_true = (
        "default_uninstall_program_removed",
        "default_uninstall_data_preserved",
        "sentinel_present_after_uninstall",
        "sentinel_present_after_reinstall",
        "reinstall_launcher_ok",
        "reinstall_discovery_ready",
    )
    for key in required_true:
        if observed.get(key) is not True:
            raise InstallSmokeError(f"install smoke observation did not prove {key}")

    hashes = [
        str(observed.get("sentinel_sha_before", "")).lower(),
        str(observed.get("sentinel_sha_after_uninstall", "")).lower(),
        str(observed.get("sentinel_sha_after_reinstall", "")).lower(),
    ]
    if any(len(value) != 64 for value in hashes) or len(set(hashes)) != 1:
        raise InstallSmokeError(
            "sentinel identity did not survive uninstall + reinstall exactly"
        )

    if first.get("fieldmedic_version") != second.get("fieldmedic_version"):
        raise InstallSmokeError("install/reinstall FieldMedic versions differ")

    first_engines = first.get("engine_discovery", {})
    second_engines = second.get("engine_discovery", {})
    for engine in ("drivemedic", "netmedic"):
        a = first_engines.get(engine, {})
        b = second_engines.get(engine, {})
        if a.get("version") != b.get("version") or not a.get("version"):
            raise InstallSmokeError(
                f"{engine} version changed or disappeared across reinstall"
            )

    body = {
        "schema": SMOKE_SCHEMA,
        "fieldmedic_version": __version__,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "platform": {
            "os_name": os.name,
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "first_install_receipt_sha256": first.get("receipt_sha256"),
        "second_install_receipt_sha256": second.get("receipt_sha256"),
        "engine_versions": {
            "drivemedic": first_engines["drivemedic"]["version"],
            "netmedic": first_engines["netmedic"]["version"],
        },
        "observations": observed,
        "status": "PASS",
        "claim_boundary": (
            "PASS proves the FieldMedic installer/default-uninstall/reinstall handoff "
            "on this recorded Windows workstation sandbox. It does not prove every "
            "Windows account, Python installation, or policy environment."
        ),
    }
    return {**body, "receipt_sha256": sha256_json(body)}


def validate_install_smoke_receipt(
    receipt: dict[str, Any],
    *,
    expected_version: str | None = None,
) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if receipt.get("schema") != SMOKE_SCHEMA:
        errors.append("unexpected install smoke schema")
    body = {
        key: value for key, value in receipt.items()
        if key != "receipt_sha256"
    }
    if receipt.get("receipt_sha256") != sha256_json(body):
        errors.append("install smoke receipt fingerprint mismatch")
    if expected_version and receipt.get("fieldmedic_version") != expected_version:
        errors.append("install smoke FieldMedic version mismatch")
    if receipt.get("platform", {}).get("os_name") != "nt":
        errors.append("install smoke was not recorded on Windows")
    if receipt.get("status") != "PASS":
        errors.append("install smoke status is not PASS")
    observed = receipt.get("observations", {})
    for key in (
        "default_uninstall_program_removed",
        "default_uninstall_data_preserved",
        "sentinel_present_after_uninstall",
        "sentinel_present_after_reinstall",
        "reinstall_launcher_ok",
        "reinstall_discovery_ready",
    ):
        if observed.get(key) is not True:
            errors.append(f"install smoke missing proof: {key}")
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
        receipt = _load_object(path)
        valid, errors = validate_install_smoke_receipt(
            receipt,
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
        "receipt_sha256": receipt.get("receipt_sha256"),
        "errors": errors,
    }


def write_install_smoke_receipt(
    output: Path,
    *,
    first_install_receipt: Path,
    second_install_receipt: Path,
    observation: Path,
) -> dict[str, Any]:
    receipt = build_install_smoke_receipt(
        first_install_receipt=first_install_receipt,
        second_install_receipt=second_install_receipt,
        observation=observation,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt
