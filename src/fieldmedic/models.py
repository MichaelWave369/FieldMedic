from __future__ import annotations
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class Source(str, Enum):
    DRIVEMEDIC = "drivemedic"
    NETMEDIC = "netmedic"
    AGENT_MEDIC = "agent-medic"
    OPERATOR = "operator"


class ClaimClass(str, Enum):
    OBSERVATION = "observation"
    INFERENCE = "inference"
    RECOMMENDATION = "recommendation"
    VERIFICATION = "verification"
    GOVERNANCE = "governance"


class Authority(str, Enum):
    OBSERVE = "observe"
    INFER = "infer"
    PROPOSE = "propose"
    EXECUTE = "execute"


@dataclass(frozen=True)
class EvidenceEnvelope:
    schema: str
    evidence_id: str
    case_id: str
    source: str
    source_version: str | None
    observed_at: str
    ingested_at: str
    category: str
    claim_class: str
    summary: str
    payload_sha256: str
    payload: Any
    confidence: float | None = None
    causal_claim: bool = False
    authority: str = Authority.OBSERVE.value
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RoutingDecision:
    domain: str
    specialists: tuple[str, ...]
    reasons: tuple[str, ...]
    escalate: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ActionProposal:
    action_id: str
    case_id: str
    proposed_at: str
    action_type: str
    description: str
    requested_authority: str
    reversible: bool
    evidence_ids: tuple[str, ...]
    status: str = "PROPOSED_NOT_AUTHORIZED"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
