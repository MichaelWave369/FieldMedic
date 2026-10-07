from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from . import __version__
from .discovery import discover_engines
from .external_gates import external_gate_from_home
from .hashutil import sha256_json
from .install_smoke import install_smoke_gate_from_home
from .windows_qualification import qualification_gate_from_home


PROMOTION_SCHEMA = "field-medic-stable-promotion-candidate-v1"


def build_promotion_candidate(home: Path) -> dict[str, Any]:
    discovery = discover_engines(home=home)
    drive_version = discovery.get("drivemedic", {}).get("version")
    net_version = discovery.get("netmedic", {}).get("version")

    gates = {
        "windows_install_smoke": install_smoke_gate_from_home(home),
        "windows_repair_qualification": qualification_gate_from_home(home),
        "drivemedic_lifecycle": external_gate_from_home(
            home=home,
            kind="drivemedic-lifecycle",
            expected_engine_version=drive_version,
        ),
        "netmedic_field": external_gate_from_home(
            home=home,
            kind="netmedic-field",
            expected_engine_version=net_version,
        ),
        "netmedic_license": external_gate_from_home(
            home=home,
            kind="netmedic-license",
            expected_engine_version=net_version,
        ),
    }

    required_status = {
        "windows_install_smoke": "QUALIFIED_BY_LOCAL_RECEIPT",
        "windows_repair_qualification": "QUALIFIED_BY_LOCAL_RECEIPT",
        "drivemedic_lifecycle": "QUALIFIED_BY_IMPORTED_EVIDENCE",
        "netmedic_field": "QUALIFIED_BY_IMPORTED_EVIDENCE",
        "netmedic_license": "QUALIFIED_BY_IMPORTED_EVIDENCE",
    }
    blocking = [
        {
            "gate": key,
            "expected": expected,
            "observed": gates[key].get("status"),
            "errors": gates[key].get("errors", []),
        }
        for key, expected in required_status.items()
        if gates[key].get("status") != expected
    ]
    status = "READY_FOR_STABLE_PACKAGING" if not blocking else "BLOCKED"

    body = {
        "schema": PROMOTION_SCHEMA,
        "fieldmedic_version": __version__,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": status,
        "engine_discovery": discovery,
        "gates": gates,
        "blocking_gates": blocking,
        "claim_boundary": (
            "READY_FOR_STABLE_PACKAGING means all configured release evidence gates "
            "are present and internally valid for the currently discovered engine versions. "
            "It is not itself a new measurement or independent audit of external receipts."
        ),
    }
    return {**body, "candidate_sha256": sha256_json(body)}


def write_promotion_candidate(home: Path, output: Path) -> dict[str, Any]:
    candidate = build_promotion_candidate(home)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(candidate, indent=2), encoding="utf-8")
    return candidate
