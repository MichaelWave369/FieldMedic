from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
from typing import Any

from . import __version__
from .discovery import discover_engines
from .hashutil import sha256_json
from .settings import load_engine_config


INSTALL_SCHEMA = "field-medic-windows-install-receipt-v1"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def build_install_receipt(
    *,
    home: Path,
    install_root: Path,
    runtime_root: Path,
    wheel: Path,
    launcher: Path,
    dashboard_launcher: Path,
    uninstaller: Path,
    path_added: bool,
) -> dict[str, Any]:
    required = {
        "runtime_root": runtime_root,
        "wheel": wheel,
        "launcher": launcher,
        "dashboard_launcher": dashboard_launcher,
        "uninstaller": uninstaller,
    }
    missing = [
        name for name, path in required.items()
        if not path.exists()
    ]
    if missing:
        raise ValueError(f"installation receipt paths missing: {missing}")

    body = {
        "schema": INSTALL_SCHEMA,
        "fieldmedic_version": __version__,
        "installed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "platform": {
            "os_name": os.name,
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "home": str(home.resolve()),
        "install_root": str(install_root.resolve()),
        "runtime_root": str(runtime_root.resolve()),
        "wheel": {
            "path": str(wheel.resolve()),
            "size_bytes": wheel.stat().st_size,
            "sha256": _sha256(wheel),
        },
        "launchers": {
            "fieldmedic": str(launcher.resolve()),
            "dashboard": str(dashboard_launcher.resolve()),
        },
        "uninstaller": str(uninstaller.resolve()),
        "path_added": bool(path_added),
        "engine_config": load_engine_config(home),
        "engine_discovery": discover_engines(home=home),
        "data_preserved_on_default_uninstall": True,
    }
    return {**body, "receipt_sha256": sha256_json(body)}


def validate_install_receipt(
    receipt: dict[str, Any],
    *,
    expected_version: str | None = None,
) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if receipt.get("schema") != INSTALL_SCHEMA:
        errors.append("unexpected install receipt schema")
    body = {
        key: value for key, value in receipt.items()
        if key != "receipt_sha256"
    }
    if receipt.get("receipt_sha256") != sha256_json(body):
        errors.append("install receipt fingerprint mismatch")
    if expected_version and receipt.get("fieldmedic_version") != expected_version:
        errors.append("install receipt FieldMedic version mismatch")
    if receipt.get("platform", {}).get("os_name") != "nt":
        errors.append("install receipt was not produced on Windows")
    if receipt.get("data_preserved_on_default_uninstall") is not True:
        errors.append("default uninstall data-preservation contract missing")

    for name, raw in (
        ("runtime_root", receipt.get("runtime_root")),
        ("fieldmedic launcher", receipt.get("launchers", {}).get("fieldmedic")),
        ("dashboard launcher", receipt.get("launchers", {}).get("dashboard")),
        ("uninstaller", receipt.get("uninstaller")),
    ):
        if not raw:
            errors.append(f"{name} missing from install receipt")

    wheel = receipt.get("wheel", {})
    if not wheel.get("sha256") or not wheel.get("path"):
        errors.append("wheel identity missing from install receipt")

    return not errors, errors


def install_gate_from_home(home: Path) -> dict[str, Any]:
    path = home / "installation" / "install.json"
    if not path.exists():
        return {
            "status": "UNPROVEN_BY_LOCAL_RECEIPT",
            "receipt_path": None,
            "receipt_sha256": None,
            "errors": ["install receipt not found"],
        }
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("install receipt root must be an object")
        valid, errors = validate_install_receipt(
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
            "INSTALLED_BY_LOCAL_RECEIPT"
            if valid
            else "INVALID_LOCAL_RECEIPT"
        ),
        "receipt_path": str(path),
        "receipt_sha256": value.get("receipt_sha256"),
        "errors": errors,
    }


def write_install_receipt(
    output: Path,
    **kwargs: Any,
) -> dict[str, Any]:
    receipt = build_install_receipt(**kwargs)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt
