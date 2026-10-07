from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import platform
from pathlib import Path
import sys
from typing import Any

from . import __version__
from .discovery import discover_engines
from .hashutil import sha256_json
from .repair_executors import list_repair_actions
from .windows_qualification import qualification_gate_from_home


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def package_inventory() -> list[dict[str, Any]]:
    root = Path(__file__).resolve().parent
    rows = []
    for path in sorted(root.rglob("*.py")):
        rows.append({
            "path": path.relative_to(root).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": _sha256(path),
        })
    return rows


def build_release_receipt(
    *,
    home: Path,
    drivemedic: str | None = None,
    netmedic: str | None = None,
) -> dict[str, Any]:
    discovery = discover_engines(
        drivemedic=drivemedic,
        netmedic=netmedic,
        home=home,
    )
    inventory = package_inventory()
    windows_repair_gate = qualification_gate_from_home(home)
    gates = {
        "python_runtime_supported": sys.version_info >= (3, 11),
        "drivemedic_discovered": bool(discovery["drivemedic"]["present"]),
        "netmedic_discovered": bool(discovery["netmedic"]["present"]),
        "drivemedic_lifecycle_qualified": "UNPROVEN_BY_LOCAL_RECEIPT",
        "netmedic_field_promoted": "UNPROVEN_BY_LOCAL_RECEIPT",
        "live_windows_repair_executors_qualified": windows_repair_gate["status"],
    }
    body = {
        "schema": "field-medic-release-receipt-v1",
        "fieldmedic_version": __version__,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "runtime": {
            "python": sys.version,
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "fieldmedic_home": str(home.resolve()),
        "engine_discovery": discovery,
        "registered_repair_actions": list_repair_actions(),
        "package_inventory": inventory,
        "package_inventory_sha256": sha256_json(inventory),
        "release_gates": gates,
        "qualification_receipts": {
            "windows_repair": windows_repair_gate,
        },
    }
    return {**body, "receipt_sha256": sha256_json(body)}
