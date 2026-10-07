from __future__ import annotations

from datetime import datetime, timezone
import ctypes
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import uuid
from typing import Any

from . import __version__
from .discovery import discover_engines
from .hashutil import sha256_json
from .orchestrator import AgentMedic
from .repair_executors import get_executor
from .repair_governance import (
    create_repair_grant,
    prepare_repair,
    propose_repair,
    save_json,
)
from .repair_runner import RepairRunner


QUALIFICATION_SCHEMA = "field-medic-windows-repair-qualification-v1"


class WindowsQualificationError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def is_windows_admin() -> bool:
    if os.name != "nt":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _receipt_body(receipt: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in receipt.items()
        if key != "receipt_sha256"
    }


def validate_windows_qualification_receipt(
    receipt: dict[str, Any],
    *,
    expected_version: str | None = None,
) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if receipt.get("schema") != QUALIFICATION_SCHEMA:
        errors.append("unexpected qualification schema")
    body = _receipt_body(receipt)
    if receipt.get("receipt_sha256") != sha256_json(body):
        errors.append("qualification receipt fingerprint mismatch")
    if receipt.get("status") != "PASS":
        errors.append("qualification status is not PASS")
    if expected_version and receipt.get("fieldmedic_version") != expected_version:
        errors.append("qualification FieldMedic version mismatch")
    if receipt.get("platform", {}).get("os_name") != "nt":
        errors.append("qualification was not produced on Windows")
    if receipt.get("platform", {}).get("admin") is not True:
        errors.append("qualification did not run elevated")

    tests = receipt.get("tests")
    if not isinstance(tests, dict):
        errors.append("qualification tests object missing")
        return False, errors
    for key in ("windows.process.priority", "windows.interface.metric"):
        test = tests.get(key)
        if not isinstance(test, dict):
            errors.append(f"missing qualification test: {key}")
            continue
        if test.get("status") != "PASS":
            errors.append(f"qualification test did not pass: {key}")
        if test.get("rollback_exact") is not True:
            errors.append(f"exact rollback not proven: {key}")
        if test.get("verification_status") != "MEASURED_PENDING_OPERATOR_OUTCOME":
            errors.append(f"independent verification not proven: {key}")
        if not test.get("execution_evidence_id"):
            errors.append(f"execution evidence missing: {key}")
        if not test.get("verification_evidence_id"):
            errors.append(f"verification evidence missing: {key}")
        if not test.get("rollback_evidence_id"):
            errors.append(f"rollback evidence missing: {key}")

    discovery = receipt.get("engine_discovery", {})
    for engine in ("drivemedic", "netmedic"):
        item = discovery.get(engine, {}) if isinstance(discovery, dict) else {}
        if item.get("present") is not True:
            errors.append(f"{engine} not present in qualification receipt")
        if item.get("healthy") is False:
            errors.append(f"{engine} reported unhealthy in qualification receipt")
        if not item.get("version"):
            errors.append(f"{engine} version missing in qualification receipt")

    return not errors, errors


def qualification_gate_from_home(home: Path) -> dict[str, Any]:
    latest = home / "qualification" / "windows-repair" / "latest.json"
    if not latest.exists():
        return {
            "status": "UNPROVEN_BY_LOCAL_RECEIPT",
            "receipt_path": None,
            "receipt_sha256": None,
            "errors": ["qualification receipt not found"],
        }
    try:
        receipt = json.loads(latest.read_text(encoding="utf-8"))
        if not isinstance(receipt, dict):
            raise ValueError("receipt root must be an object")
        valid, errors = validate_windows_qualification_receipt(
            receipt,
            expected_version=__version__,
        )
    except Exception as exc:
        return {
            "status": "INVALID_LOCAL_RECEIPT",
            "receipt_path": str(latest),
            "receipt_sha256": None,
            "errors": [str(exc)],
        }
    return {
        "status": (
            "QUALIFIED_BY_LOCAL_RECEIPT"
            if valid
            else "INVALID_LOCAL_RECEIPT"
        ),
        "receipt_path": str(latest),
        "receipt_sha256": receipt.get("receipt_sha256"),
        "errors": errors,
    }


def _case(home: Path, case_id: str) -> dict[str, Any]:
    path = home / "cases" / case_id / "case.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise WindowsQualificationError("qualification case root is not an object")
    return value


def _assert_changed(preflight: dict[str, Any]) -> None:
    if (
        preflight.get("state_before_sha256")
        == preflight.get("expected_applied_state_sha256")
    ):
        raise WindowsQualificationError(
            "qualification action would not change target state; choose a different temporary value"
        )


def _run_repair_test(
    *,
    home: Path,
    case: dict[str, Any],
    runner: RepairRunner,
    action_key: str,
    params: dict[str, Any],
    operator_label: str,
) -> dict[str, Any]:
    proposal = propose_repair(
        case,
        action_key=action_key,
        params=params,
    )
    executor = get_executor(action_key)
    preflight = prepare_repair(
        proposal,
        executor=executor,
        ttl_minutes=10,
    )
    _assert_changed(preflight)
    grant = create_repair_grant(
        proposal,
        preflight,
        operator_label=operator_label,
        ttl_minutes=15,
    )

    execution: dict[str, Any] | None = None
    verification: dict[str, Any] | None = None
    rollback: dict[str, Any] | None = None
    caught: str | None = None
    try:
        execution = runner.execute(proposal, preflight, grant)
        if execution.get("status") != "EXECUTED_PENDING_OUTCOME_VERIFICATION":
            raise WindowsQualificationError(
                f"repair did not remain applied for verification: {execution.get('status')}"
            )
        verification = runner.verify(execution)
        if verification.get("status") != "MEASURED_PENDING_OPERATOR_OUTCOME":
            raise WindowsQualificationError(
                f"repair verification did not reach expected state: {verification.get('status')}"
            )
        rollback = runner.rollback(execution)
    except Exception as exc:
        caught = str(exc)
        if execution and execution.get("status") == "EXECUTED_PENDING_OUTCOME_VERIFICATION":
            try:
                rollback = runner.rollback(execution)
            except Exception as rollback_exc:
                caught = (
                    f"{caught}; rollback attempt also failed: {rollback_exc}"
                )
    if execution is None:
        raise WindowsQualificationError(caught or "repair execution did not produce a receipt")
    if rollback is None:
        raise WindowsQualificationError(caught or "repair rollback did not produce a receipt")
    exact = rollback.get("status") in {"ROLLED_BACK", "ALREADY_AT_ROLLBACK_STATE"}
    if not exact:
        raise WindowsQualificationError(
            caught or f"repair rollback status was not exact: {rollback.get('status')}"
        )
    if caught:
        raise WindowsQualificationError(caught)

    return {
        "status": "PASS",
        "action_key": action_key,
        "proposal_id": proposal.proposal_id,
        "proposal_sha256": proposal.sha256,
        "preflight_sha256": preflight["preflight_sha256"],
        "grant_sha256": grant["grant_sha256"],
        "execution_status": execution["status"],
        "verification_status": verification["status"],
        "rollback_status": rollback["status"],
        "rollback_exact": True,
        "execution_evidence_id": execution.get("execution_evidence_id"),
        "verification_evidence_id": verification.get("verification_evidence_id"),
        "rollback_evidence_id": rollback.get("rollback_evidence_id"),
        "state_before_sha256": preflight["state_before_sha256"],
        "expected_applied_state_sha256": preflight[
            "expected_applied_state_sha256"
        ],
        "rollback_state_sha256": rollback.get("rollback", {}).get(
            "state_sha256"
        ),
    }


def _spawn_priority_helper() -> subprocess.Popen[str]:
    return subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import time; time.sleep(300)",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )


def run_windows_repair_qualification(
    *,
    home: Path,
    drivemedic: str | None,
    netmedic: str | None,
    interface_index: int,
    address_family: str,
    temporary_metric: int,
    operator_label: str,
) -> dict[str, Any]:
    if os.name != "nt":
        raise WindowsQualificationError(
            "live Windows repair qualification must run on Windows"
        )
    if not is_windows_admin():
        raise WindowsQualificationError(
            "live Windows repair qualification requires an elevated Administrator terminal"
        )
    if not operator_label.strip():
        raise WindowsQualificationError("operator label is required")

    discovery = discover_engines(
        drivemedic=drivemedic,
        netmedic=netmedic,
    )
    if not discovery.get("ready_for_diagnostics"):
        raise WindowsQualificationError(
            "DriveMedic and NetMedic must both be discovered and healthy enough for diagnostics"
        )
    drive_path = discovery["drivemedic"]["path"]
    net_path = discovery["netmedic"]["path"]
    if not drive_path or not net_path:
        raise WindowsQualificationError("engine discovery did not resolve executable paths")

    qualification_id = "winqual-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    case_id = f"case-{qualification_id}"
    agent = AgentMedic(home)
    agent.doctor(
        "FieldMedic live Windows bounded repair qualification for host and network executors",
        drive_path,
        net_path,
        case_id,
        discover_models=False,
        local_reasoning=False,
    )
    case = _case(home, case_id)
    runner = RepairRunner(
        home=home,
        drivemedic=drive_path,
        netmedic=net_path,
    )

    tests: dict[str, Any] = {}
    errors: list[str] = []
    helper = _spawn_priority_helper()
    try:
        time.sleep(0.25)
        try:
            tests["windows.process.priority"] = _run_repair_test(
                home=home,
                case=case,
                runner=runner,
                action_key="windows.process.priority",
                params={
                    "pid": helper.pid,
                    "priority": "BelowNormal",
                },
                operator_label=operator_label,
            )
        except Exception as exc:
            errors.append(f"windows.process.priority: {exc}")
            tests["windows.process.priority"] = {
                "status": "FAIL",
                "error": str(exc),
                "rollback_exact": False,
            }

        try:
            tests["windows.interface.metric"] = _run_repair_test(
                home=home,
                case=case,
                runner=runner,
                action_key="windows.interface.metric",
                params={
                    "interface_index": int(interface_index),
                    "address_family": address_family,
                    "metric": int(temporary_metric),
                },
                operator_label=operator_label,
            )
        except Exception as exc:
            errors.append(f"windows.interface.metric: {exc}")
            tests["windows.interface.metric"] = {
                "status": "FAIL",
                "error": str(exc),
                "rollback_exact": False,
            }
    finally:
        helper.terminate()
        try:
            helper.wait(timeout=5)
        except Exception:
            helper.kill()

    status = (
        "PASS"
        if not errors
        and all(item.get("status") == "PASS" for item in tests.values())
        else "FAIL"
    )
    body = {
        "schema": QUALIFICATION_SCHEMA,
        "qualification_id": qualification_id,
        "fieldmedic_version": __version__,
        "generated_at": _utc_now(),
        "status": status,
        "case_id": case_id,
        "operator_label": operator_label,
        "operator_label_semantics": (
            "local operator label; not independently verified identity"
        ),
        "platform": {
            "os_name": os.name,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": sys.version,
            "admin": True,
        },
        "engine_discovery": discovery,
        "requested_interface_test": {
            "interface_index": int(interface_index),
            "address_family": address_family,
            "temporary_metric": int(temporary_metric),
        },
        "tests": tests,
        "errors": errors,
        "claim_boundary": (
            "PASS qualifies the bounded executor apply/measure/rollback path on this "
            "recorded Windows environment; it does not qualify every Windows machine, "
            "driver, interface, or workload."
        ),
    }
    receipt = {**body, "receipt_sha256": sha256_json(body)}

    root = home / "qualification" / "windows-repair"
    root.mkdir(parents=True, exist_ok=True)
    timestamped = root / f"{qualification_id}.json"
    save_json(timestamped, receipt)
    save_json(root / "latest.json", receipt)
    return receipt
