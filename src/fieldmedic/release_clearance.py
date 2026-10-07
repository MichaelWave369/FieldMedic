from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from . import __version__
from .discovery import discover_engines
from .external_gates import (
    drivemedic_lifecycle_gate_from_home,
    netmedic_field_gate_from_home,
)
from .hashutil import sha256_json
from .install_smoke import install_smoke_gate_from_home
from .installation import install_gate_from_home
from .licensing import netmedic_license_gate_from_home
from .windows_qualification import qualification_gate_from_home


CLEARANCE_SCHEMA = "field-medic-release-clearance-v1"


def _status_ok(gate: dict[str, Any], expected: str) -> bool:
    return gate.get("status") == expected


def _contains_version(observed: str | None, native: str | None) -> bool:
    if not observed or not native:
        return False
    return str(native).lower() in str(observed).lower()


def build_release_clearance(
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
    install = install_gate_from_home(home)
    install_smoke = install_smoke_gate_from_home(home)
    repair = qualification_gate_from_home(home)
    drive = drivemedic_lifecycle_gate_from_home(home)
    net = netmedic_field_gate_from_home(home)
    net_license = netmedic_license_gate_from_home(home)

    drive_native_version = (
        drive.get("native", {}).get("version")
        if isinstance(drive.get("native"), dict)
        else None
    )
    net_native_version = (
        net.get("native", {}).get("version")
        if isinstance(net.get("native"), dict)
        else None
    )
    drive_observed = discovery.get("drivemedic", {}).get("version")
    net_observed = discovery.get("netmedic", {}).get("version")

    checks = {
        "engine_discovery_ready": bool(discovery.get("ready_for_diagnostics")),
        "windows_install_handoff": _status_ok(
            install,
            "INSTALLED_BY_LOCAL_RECEIPT",
        ),
        "windows_install_smoke": _status_ok(
            install_smoke,
            "QUALIFIED_BY_LOCAL_RECEIPT",
        ),
        "windows_repair_qualification": _status_ok(
            repair,
            "QUALIFIED_BY_LOCAL_RECEIPT",
        ),
        "drivemedic_lifecycle": _status_ok(
            drive,
            "LIFECYCLE_QUALIFIED_BY_IMPORTED_NATIVE_RECEIPT",
        ),
        "netmedic_field": _status_ok(
            net,
            "FIELD_VERIFIED_BY_IMPORTED_NATIVE_RECEIPT",
        ),
        "netmedic_public_license": _status_ok(
            net_license,
            "PUBLIC_MIT_LICENSE_VERIFIED_BY_SOURCE_HANDOFF",
        ),
        "drivemedic_version_alignment": _contains_version(
            drive_observed,
            drive_native_version,
        ),
        "netmedic_version_alignment": _contains_version(
            net_observed,
            net_native_version,
        ),
    }

    all_gates = {
        "windows_install_handoff": install,
        "windows_install_smoke": install_smoke,
        "windows_repair": repair,
        "drivemedic_lifecycle": drive,
        "netmedic_field": net,
        "netmedic_license": net_license,
    }
    invalid = any(
        str(gate.get("status", "")).startswith("INVALID")
        for gate in all_gates.values()
    )
    if invalid:
        status = "BLOCKED_INVALID_EVIDENCE"
    elif all(checks.values()):
        status = "ELIGIBLE_FOR_STABLE_PACKAGING"
    else:
        status = "RELEASE_CLEARANCE_INCOMPLETE"

    body = {
        "schema": CLEARANCE_SCHEMA,
        "fieldmedic_version": __version__,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": status,
        "checks": checks,
        "engine_discovery": discovery,
        "gates": all_gates,
        "version_alignment": {
            "drivemedic": {
                "observed": drive_observed,
                "native_evidence": drive_native_version,
                "match": checks["drivemedic_version_alignment"],
            },
            "netmedic": {
                "observed": net_observed,
                "native_evidence": net_native_version,
                "match": checks["netmedic_version_alignment"],
            },
        },
        "next_gate": (
            "BUILD_FINAL_STABLE_PACKAGE_AND_HASH_RECEIPT"
            if status == "ELIGIBLE_FOR_STABLE_PACKAGING"
            else "SATISFY_OR_REPAIR_REMAINING_CLEARANCE_CHECKS"
        ),
        "stable_release_claim": False,
        "claim_boundary": (
            "Release clearance only determines whether the recorded local/native "
            "qualification evidence is sufficient to build a stable candidate. "
            "It does not publish, tag, sign, or claim a stable release."
        ),
    }
    return {**body, "receipt_sha256": sha256_json(body)}


def write_release_clearance(
    output: Path,
    **kwargs: Any,
) -> dict[str, Any]:
    receipt = build_release_clearance(**kwargs)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt
