from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import uuid
from typing import Any

from .hashutil import sha256_json


_ALLOWED_SCOPES = {
    "netmedic.protocol.freeze",
    "netmedic.protocol.preflight",
    "netmedic.protocol.capture",
    "netmedic.protocol.matched",
}


class ExperimentApprovalError(PermissionError):
    pass


@dataclass(frozen=True)
class ExperimentProposal:
    schema: str
    proposal_id: str
    case_id: str
    netmedic_case: str
    name: str
    design_key: str
    arm_a: str
    arm_b: str
    test_label: str
    trials: int
    window_minutes: int
    controls: tuple[tuple[str, str], ...]
    evidence_ids: tuple[str, ...]
    causal_claim: bool = False
    requested_authority: str = "propose"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def sha256(self) -> str:
        return sha256_json(self.to_dict())


def propose_experiment(
    *,
    case_id: str,
    netmedic_case: str,
    name: str,
    design_key: str,
    arm_a: str,
    arm_b: str,
    test_label: str,
    trials: int = 6,
    window_minutes: int = 5,
    controls: dict[str, str] | None = None,
    evidence_ids: list[str] | tuple[str, ...] = (),
) -> ExperimentProposal:
    if not all(str(value).strip() for value in (
        case_id, netmedic_case, name, design_key, arm_a, arm_b, test_label
    )):
        raise ValueError("experiment proposal fields must be non-empty")
    if arm_a == arm_b:
        raise ValueError("experiment arms must differ")
    if not 1 <= trials <= 100:
        raise ValueError("trials must be between 1 and 100")
    if not 1 <= window_minutes <= 120:
        raise ValueError("window_minutes must be between 1 and 120")
    normalized_controls = tuple(sorted((str(k), str(v)) for k, v in (controls or {}).items()))
    return ExperimentProposal(
        schema="field-medic-experiment-proposal-v1",
        proposal_id=f"exp-{uuid.uuid4().hex[:12]}",
        case_id=case_id,
        netmedic_case=netmedic_case,
        name=name,
        design_key=design_key,
        arm_a=arm_a,
        arm_b=arm_b,
        test_label=test_label,
        trials=trials,
        window_minutes=window_minutes,
        controls=normalized_controls,
        evidence_ids=tuple(evidence_ids),
    )


def suggest_experiment_template(
    *,
    symptom: str,
    case_id: str,
    netmedic_case: str | None,
    evidence_ids: list[str] | tuple[str, ...],
) -> ExperimentProposal | None:
    if not netmedic_case:
        return None
    text = symptom.lower()
    if any(token in text for token in ("wifi", "wi-fi", "wireless", "ethernet")):
        return propose_experiment(
            case_id=case_id,
            netmedic_case=netmedic_case,
            name="Wi-Fi vs Ethernet",
            design_key="connection",
            arm_a="wifi",
            arm_b="ethernet",
            test_label="ethernet-ab",
            controls={"vpn": "off"},
            evidence_ids=evidence_ids,
        )
    if "vpn" in text:
        return propose_experiment(
            case_id=case_id,
            netmedic_case=netmedic_case,
            name="VPN Off vs On",
            design_key="vpn",
            arm_a="off",
            arm_b="on",
            test_label="vpn-ab",
            evidence_ids=evidence_ids,
        )
    if any(token in text for token in ("dns", "resolver", "resolve")):
        # Resolver values are environment-specific. Do not invent them.
        return None
    return None


def create_approval(
    proposal: ExperimentProposal,
    *,
    operator_label: str,
    scopes: list[str] | tuple[str, ...],
    ttl_minutes: int = 30,
    confirmations: dict[str, bool] | None = None,
) -> dict[str, Any]:
    if not operator_label.strip():
        raise ValueError("operator_label is required")
    unique_scopes = list(dict.fromkeys(scopes))
    invalid = [scope for scope in unique_scopes if scope not in _ALLOWED_SCOPES]
    if invalid:
        raise ValueError(f"unsupported experiment approval scopes: {invalid}")
    if not unique_scopes:
        raise ValueError("at least one approval scope is required")
    if not 1 <= ttl_minutes <= 240:
        raise ValueError("ttl_minutes must be between 1 and 240")
    now = datetime.now(timezone.utc)
    confirm = confirmations or {}
    return {
        "schema": "field-medic-experiment-approval-v1",
        "approval_id": f"approval-{uuid.uuid4().hex[:12]}",
        "proposal_id": proposal.proposal_id,
        "proposal_sha256": proposal.sha256,
        "case_id": proposal.case_id,
        "netmedic_case": proposal.netmedic_case,
        "operator_label": operator_label,
        "operator_label_semantics": "local label supplied by operator; not independently verified identity",
        "approved_scopes": unique_scopes,
        "confirmations": {
            "arm": bool(confirm.get("arm", False)),
            "machine_stable": bool(confirm.get("machine_stable", False)),
            "test_context": bool(confirm.get("test_context", False)),
            "controls": sorted(str(item) for item in confirm.get("controls", [])),
        },
        "issued_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": (now + timedelta(minutes=ttl_minutes)).isoformat().replace("+00:00", "Z"),
        "authority": "operator-approved-diagnostic-measurement",
        "repair_authority": False,
    }


def _parse_utc(text: str) -> datetime:
    value = text[:-1] + "+00:00" if text.endswith("Z") else text
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class ExperimentGate:
    def require(
        self,
        *,
        proposal: ExperimentProposal,
        approval: dict[str, Any],
        scope: str,
        now: datetime | None = None,
        require_physical_confirmations: bool = False,
    ) -> None:
        if scope not in _ALLOWED_SCOPES:
            raise ExperimentApprovalError(f"unsupported experiment scope: {scope}")
        if approval.get("schema") != "field-medic-experiment-approval-v1":
            raise ExperimentApprovalError("invalid experiment approval schema")
        if approval.get("proposal_id") != proposal.proposal_id:
            raise ExperimentApprovalError("approval proposal_id mismatch")
        if approval.get("proposal_sha256") != proposal.sha256:
            raise ExperimentApprovalError("approval does not match current proposal bytes")
        if approval.get("case_id") != proposal.case_id:
            raise ExperimentApprovalError("approval case mismatch")
        if approval.get("netmedic_case") != proposal.netmedic_case:
            raise ExperimentApprovalError("approval NetMedic case mismatch")
        if approval.get("repair_authority") is not False:
            raise ExperimentApprovalError("experiment approval must not grant repair authority")
        if scope not in approval.get("approved_scopes", []):
            raise ExperimentApprovalError(f"scope not approved: {scope}")

        instant = now or datetime.now(timezone.utc)
        try:
            expires = _parse_utc(str(approval["expires_at"]))
        except Exception as exc:
            raise ExperimentApprovalError("approval expiration is invalid") from exc
        if instant >= expires:
            raise ExperimentApprovalError("experiment approval has expired")

        if require_physical_confirmations:
            confirm = approval.get("confirmations", {})
            missing = [
                key for key in ("arm", "machine_stable", "test_context")
                if not confirm.get(key)
            ]
            required_controls = {key for key, _ in proposal.controls}
            confirmed_controls = set(confirm.get("controls", []))
            if not required_controls.issubset(confirmed_controls):
                missing.append("controls")
            if missing:
                raise ExperimentApprovalError(
                    f"capture requires fresh operator confirmations: {missing}"
                )


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_proposal(path: Path) -> ExperimentProposal:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != "field-medic-experiment-proposal-v1":
        raise ValueError("invalid experiment proposal schema")
    return ExperimentProposal(
        schema=payload["schema"],
        proposal_id=payload["proposal_id"],
        case_id=payload["case_id"],
        netmedic_case=payload["netmedic_case"],
        name=payload["name"],
        design_key=payload["design_key"],
        arm_a=payload["arm_a"],
        arm_b=payload["arm_b"],
        test_label=payload["test_label"],
        trials=int(payload["trials"]),
        window_minutes=int(payload["window_minutes"]),
        controls=tuple(tuple(item) for item in payload.get("controls", [])),
        evidence_ids=tuple(payload.get("evidence_ids", [])),
        causal_claim=bool(payload.get("causal_claim", False)),
        requested_authority=payload.get("requested_authority", "propose"),
    )


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON document root must be an object")
    return payload
