from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import uuid
from typing import Any

from .hashutil import sha256_json
from .repair_executors import (
    SPECS,
    BoundedRepairExecutor,
    get_executor,
    normalize_params,
)


class RepairDenied(PermissionError):
    pass


def _utc_now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _utc_text(value: datetime | None = None) -> str:
    return (value or _utc_now_dt()).isoformat().replace("+00:00", "Z")


def _parse_utc(text: str) -> datetime:
    value = text[:-1] + "+00:00" if text.endswith("Z") else text
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass(frozen=True)
class RepairProposal:
    schema: str
    proposal_id: str
    case_id: str
    action_key: str
    params: dict[str, Any]
    evidence_ids: tuple[str, ...]
    created_at: str
    reversible: bool = True
    requested_authority: str = "execute"
    causal_claim: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def sha256(self) -> str:
        return sha256_json(self.to_dict())


def _source_evidence(case: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item for item in case.get("evidence", [])
        if item.get("source") in {"drivemedic", "netmedic"}
        and item.get("evidence_id")
    ]


def validate_case_for_repair(
    case: dict[str, Any],
    *,
    action_key: str,
    evidence_ids: tuple[str, ...] | list[str],
) -> None:
    if action_key not in SPECS:
        raise RepairDenied(f"unknown repair action: {action_key}")
    if case.get("correlation", {}).get("contradictions"):
        raise RepairDenied(
            "repair denied while same-subject contradictions remain unresolved"
        )
    source_rows = _source_evidence(case)
    if not source_rows:
        raise RepairDenied(
            "repair denied because no DriveMedic/NetMedic source evidence exists"
        )
    available = {item["evidence_id"] for item in source_rows}
    supplied = set(evidence_ids)
    if not supplied:
        raise RepairDenied("repair proposal must cite source evidence")
    unknown = sorted(supplied - available)
    if unknown:
        raise RepairDenied(
            f"repair proposal cites non-source or unknown evidence IDs: {unknown}"
        )
    required_source = SPECS[action_key].required_source
    if not any(item.get("source") == required_source for item in source_rows):
        raise RepairDenied(
            f"{action_key} requires current {required_source} evidence"
        )


def propose_repair(
    case: dict[str, Any],
    *,
    action_key: str,
    params: dict[str, Any],
) -> RepairProposal:
    normalized = normalize_params(action_key, params)
    evidence_ids = tuple(
        item["evidence_id"] for item in _source_evidence(case)
    )
    validate_case_for_repair(
        case,
        action_key=action_key,
        evidence_ids=evidence_ids,
    )
    return RepairProposal(
        schema="field-medic-repair-proposal-v1",
        proposal_id=f"repair-{uuid.uuid4().hex[:12]}",
        case_id=str(case["case_id"]),
        action_key=action_key,
        params=normalized,
        evidence_ids=evidence_ids,
        created_at=_utc_text(),
    )


def prepare_repair(
    proposal: RepairProposal,
    *,
    executor: BoundedRepairExecutor | None = None,
    ttl_minutes: int = 10,
) -> dict[str, Any]:
    if not 1 <= ttl_minutes <= 30:
        raise ValueError("repair preflight ttl_minutes must be between 1 and 30")
    actual = executor or get_executor(proposal.action_key)
    before = actual.inspect(proposal.params)
    expected = actual.expected_applied_state(proposal.params, before)
    now = _utc_now_dt()
    body = {
        "schema": "field-medic-repair-preflight-v1",
        "preflight_id": f"repair-preflight-{uuid.uuid4().hex[:12]}",
        "proposal_id": proposal.proposal_id,
        "proposal_sha256": proposal.sha256,
        "case_id": proposal.case_id,
        "action_key": proposal.action_key,
        "state_before": before,
        "state_before_sha256": sha256_json(before),
        "expected_applied_state": expected,
        "expected_applied_state_sha256": sha256_json(expected),
        "rollback_state": before,
        "prepared_at": _utc_text(now),
        "expires_at": _utc_text(now + timedelta(minutes=ttl_minutes)),
        "rollback_required": True,
        "generic_shell_authorized": False,
    }
    return {**body, "preflight_sha256": sha256_json(body)}


def create_repair_grant(
    proposal: RepairProposal,
    preflight: dict[str, Any],
    *,
    operator_label: str,
    ttl_minutes: int = 15,
) -> dict[str, Any]:
    if not operator_label.strip():
        raise ValueError("operator_label is required")
    if not 1 <= ttl_minutes <= 30:
        raise ValueError("repair grant ttl_minutes must be between 1 and 30")
    if preflight.get("proposal_sha256") != proposal.sha256:
        raise RepairDenied("preflight does not match proposal")
    now = _utc_now_dt()
    body = {
        "schema": "field-medic-repair-grant-v1",
        "grant_id": f"repair-grant-{uuid.uuid4().hex[:12]}",
        "proposal_id": proposal.proposal_id,
        "proposal_sha256": proposal.sha256,
        "preflight_id": preflight["preflight_id"],
        "preflight_sha256": preflight["preflight_sha256"],
        "case_id": proposal.case_id,
        "action_key": proposal.action_key,
        "operator_label": operator_label,
        "operator_label_semantics": (
            "local operator label; not independently verified identity"
        ),
        "approved_scopes": ["repair.execute", "repair.rollback"],
        "issued_at": _utc_text(now),
        "expires_at": _utc_text(now + timedelta(minutes=ttl_minutes)),
        "generic_shell_authorized": False,
        "authority": "bounded-repair",
    }
    return {**body, "grant_sha256": sha256_json(body)}


class RepairGate:
    def require_execute(
        self,
        *,
        proposal: RepairProposal,
        preflight: dict[str, Any],
        grant: dict[str, Any],
        case: dict[str, Any],
        now: datetime | None = None,
    ) -> None:
        if proposal.action_key not in SPECS:
            raise RepairDenied("unregistered repair action")
        validate_case_for_repair(
            case,
            action_key=proposal.action_key,
            evidence_ids=proposal.evidence_ids,
        )
        if not proposal.reversible:
            raise RepairDenied("bounded repair proposal must be reversible")
        if preflight.get("schema") != "field-medic-repair-preflight-v1":
            raise RepairDenied("invalid repair preflight schema")
        if grant.get("schema") != "field-medic-repair-grant-v1":
            raise RepairDenied("invalid repair grant schema")
        if preflight.get("proposal_sha256") != proposal.sha256:
            raise RepairDenied("preflight proposal hash mismatch")
        pbody = {
            key: value for key, value in preflight.items()
            if key != "preflight_sha256"
        }
        if preflight.get("preflight_sha256") != sha256_json(pbody):
            raise RepairDenied("preflight fingerprint validation failed")
        gbody = {
            key: value for key, value in grant.items()
            if key != "grant_sha256"
        }
        if grant.get("grant_sha256") != sha256_json(gbody):
            raise RepairDenied("repair grant fingerprint validation failed")
        if grant.get("proposal_sha256") != proposal.sha256:
            raise RepairDenied("grant proposal hash mismatch")
        if grant.get("preflight_sha256") != preflight.get("preflight_sha256"):
            raise RepairDenied("grant preflight hash mismatch")
        if grant.get("case_id") != proposal.case_id:
            raise RepairDenied("grant case mismatch")
        if grant.get("action_key") != proposal.action_key:
            raise RepairDenied("grant action mismatch")
        if grant.get("generic_shell_authorized") is not False:
            raise RepairDenied("repair grant must not authorize a generic shell")
        if "repair.execute" not in grant.get("approved_scopes", []):
            raise RepairDenied("repair.execute scope not authorized")
        instant = now or _utc_now_dt()
        if instant >= _parse_utc(str(preflight["expires_at"])):
            raise RepairDenied("repair preflight expired; inspect state again")
        if instant >= _parse_utc(str(grant["expires_at"])):
            raise RepairDenied("repair grant expired; re-authorize")

    def require_rollback_receipt(
        self,
        execution: dict[str, Any],
    ) -> None:
        if execution.get("schema") != "field-medic-repair-execution-v1":
            raise RepairDenied("invalid repair execution receipt")
        grant = execution.get("grant", {})
        if "repair.rollback" not in grant.get("approved_scopes", []):
            raise RepairDenied("original repair grant did not authorize rollback")
        if grant.get("generic_shell_authorized") is not False:
            raise RepairDenied("rollback receipt contains invalid generic authority")


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON root must be an object")
    return value


def load_proposal(path: Path) -> RepairProposal:
    value = load_json(path)
    if value.get("schema") != "field-medic-repair-proposal-v1":
        raise ValueError("invalid repair proposal schema")
    proposal = RepairProposal(
        schema=value["schema"],
        proposal_id=value["proposal_id"],
        case_id=value["case_id"],
        action_key=value["action_key"],
        params=normalize_params(value["action_key"], value["params"]),
        evidence_ids=tuple(value.get("evidence_ids", [])),
        created_at=value["created_at"],
        reversible=bool(value.get("reversible", True)),
        requested_authority=value.get("requested_authority", "execute"),
        causal_claim=bool(value.get("causal_claim", False)),
    )
    if proposal.causal_claim:
        raise ValueError("repair proposal may not assert causation")
    return proposal
