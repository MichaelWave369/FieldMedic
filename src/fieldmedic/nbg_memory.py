from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import uuid
from typing import Any, Iterable

from .hashutil import sha256_json


ORIGIN_WEIGHT = {
    "VERIFIED": 1.00,
    "OBSERVED": 0.85,
    "INFERRED": 0.45,
    "SIMULATED": 0.25,
    "DREAMED": 0.15,
    "UNKNOWN": 0.00,
}
VERIFIED_OUTCOMES = {
    "VERIFIED_SUCCESS",
    "VERIFIED_FAILURE",
    "VERIFIED_NO_EFFECT",
    "VERIFIED_CONTRADICTION",
}
VALID_OUTCOMES = VERIFIED_OUTCOMES | {"UNRESOLVED"}


class MemoryErrorBase(RuntimeError):
    pass


class MemoryAdmissionError(MemoryErrorBase):
    pass


class MemoryConflictError(MemoryErrorBase):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def stable_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def fnv1a32(text: str) -> str:
    raw = text.encode("utf-16-le", errors="surrogatepass")
    value = 2166136261
    for index in range(0, len(raw), 2):
        unit = raw[index] | (raw[index + 1] << 8)
        value ^= unit
        value = (value * 16777619) & 0xFFFFFFFF
    return f"fnv1a32:{value:08x}"


def nbg_fingerprint(value: Any) -> str:
    return fnv1a32(value if isinstance(value, str) else stable_json(value))


def normalize_evidence(
    *,
    evidence_id: str,
    kind: str,
    source: Any = None,
    known_time: Any = None,
    valid_time: Any = None,
    details: Any = None,
) -> dict[str, Any]:
    if not evidence_id or not kind:
        raise ValueError("evidence_id and kind are required")
    body = {
        "evidenceId": evidence_id,
        "kind": kind,
        "source": source,
        "knownTime": known_time,
        "validTime": valid_time,
        "details": details,
    }
    return {**body, "evidenceFingerprint": nbg_fingerprint(body)}


def _dedupe_evidence(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for item in items:
        prior = by_id.get(item["evidenceId"])
        if prior is not None and stable_json(prior) != stable_json(item):
            raise MemoryConflictError(
                f"conflicting evidence id: {item['evidenceId']}"
            )
        by_id[item["evidenceId"]] = item
    return [by_id[key] for key in sorted(by_id)]


def create_nbg_memory(
    *,
    memory_id: str,
    content: Any,
    origin: str,
    confidence: float,
    evidence: Iterable[dict[str, Any]],
    root_memory_id: str | None = None,
    parent_memory_id: str | None = None,
    transition_receipt_ids: Iterable[str] = (),
    source_memory_ids: Iterable[str] = (),
    compacted_from: Iterable[str] = (),
    valid_time: Any = None,
    known_time: Any = None,
    tags: Iterable[str] = (),
    retainable: bool = True,
    reasoning_usable: bool = True,
    action_authorized: bool = False,
) -> dict[str, Any]:
    if origin not in ORIGIN_WEIGHT:
        raise ValueError(f"unsupported NBG epistemic origin: {origin}")
    if not 0 <= float(confidence) <= 1:
        raise ValueError("confidence must be in [0,1]")
    if action_authorized:
        raise ValueError("FieldMedic diagnostic memory cannot authorize action")

    record = {
        "schemaVersion": "NBG_EPISTEMIC_1",
        "memoryId": memory_id,
        "content": content,
        "epistemic": {
            "origin": origin,
            "confidence": float(confidence),
            "evidence": _dedupe_evidence(evidence),
            "lineage": {
                "rootMemoryId": root_memory_id or memory_id,
                "parentMemoryId": parent_memory_id,
                "transitionReceiptIds": list(dict.fromkeys(transition_receipt_ids)),
                "sourceMemoryIds": list(dict.fromkeys(source_memory_ids)),
                "compactedFrom": list(dict.fromkeys(compacted_from)),
            },
            "authority": {
                "retainable": bool(retainable),
                "reasoningUsable": bool(reasoning_usable),
                "actionAuthorized": False,
            },
        },
        "validTime": valid_time,
        "knownTime": known_time,
        "tags": sorted(set(tags)),
    }
    return {**record, "recordFingerprint": nbg_fingerprint(record)}


def _evidence_kind(item: dict[str, Any]) -> str:
    if item.get("claim_class") == "verification":
        return "VERIFICATION"
    if item.get("source") in {"drivemedic", "netmedic"}:
        return "MEASUREMENT"
    if item.get("claim_class") == "observation":
        return "OBSERVATION"
    return "EXTERNAL_EVIDENCE"


def case_to_inferred_memory(case: dict[str, Any]) -> dict[str, Any]:
    case_id = str(case["case_id"])
    evidence_rows = []
    for item in case.get("evidence", []):
        evidence_id = item.get("evidence_id")
        if not evidence_id:
            continue
        evidence_rows.append(normalize_evidence(
            evidence_id=evidence_id,
            kind=_evidence_kind(item),
            source=item.get("source"),
            known_time=item.get("ingested_at"),
            valid_time=item.get("observed_at"),
            details={
                "category": item.get("category"),
                "claimClass": item.get("claim_class"),
                "payloadSha256": item.get("payload_sha256"),
            },
        ))

    routing = case.get("routing", {})
    specialist_ids = case.get("specialist_plan", {}).get("specialist_ids", [])
    synthesis = case.get("synthesis", {})
    claims = synthesis.get("claims", [])

    content = {
        "schema": "field-medic-diagnostic-memory-v1",
        "caseId": case_id,
        "symptom": case.get("symptom", ""),
        "domain": routing.get("domain", "unknown"),
        "specialistIds": specialist_ids,
        "claims": claims,
        "outcome": {
            "status": "UNRESOLVED",
            "details": None,
        },
        "experimentProposal": (
            case.get("experiment_proposal", {}).get("proposal")
            if isinstance(case.get("experiment_proposal"), dict)
            else None
        ),
        "causalClaim": False,
    }

    association = float(case.get("correlation", {}).get(
        "temporal_association_strength", 0.0
    ))
    confidence = min(0.75, max(0.25, 0.35 + association * 0.4))

    observed_times = [
        item.get("observed_at")
        for item in case.get("evidence", [])
        if item.get("observed_at")
    ]
    known_times = [
        item.get("ingested_at")
        for item in case.get("evidence", [])
        if item.get("ingested_at")
    ]
    valid_time = min(observed_times) if observed_times else None
    known_time = max(known_times) if known_times else utc_now()

    tags = [
        "fieldmedic",
        f"domain:{content['domain']}",
        *[f"specialist:{item}" for item in specialist_ids],
    ]
    return create_nbg_memory(
        memory_id=f"fieldmedic:{case_id}:inferred",
        content=content,
        origin="INFERRED",
        confidence=confidence,
        evidence=evidence_rows,
        valid_time=valid_time,
        known_time=known_time,
        tags=tags,
    )


def derive_verified_outcome(
    source_memory: dict[str, Any],
    *,
    outcome: str,
    verification_evidence_id: str,
    details: str | None = None,
    source: str = "operator-verification",
    known_time: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if outcome not in VERIFIED_OUTCOMES:
        raise MemoryAdmissionError(
            f"verified derivation requires one of {sorted(VERIFIED_OUTCOMES)}"
        )
    if source_memory.get("epistemic", {}).get("origin") != "INFERRED":
        raise MemoryAdmissionError("verified outcome must derive from INFERRED memory")
    existing = {
        item["evidenceId"]
        for item in source_memory["epistemic"]["evidence"]
    }
    if not verification_evidence_id or verification_evidence_id in existing:
        raise MemoryAdmissionError(
            "verification requires a new evidence ID not already on the source memory"
        )

    evidence = normalize_evidence(
        evidence_id=verification_evidence_id,
        kind="VERIFICATION",
        source=source,
        known_time=known_time or utc_now(),
        details={"outcome": outcome, "details": details},
    )
    transition_id = f"memory-transition-{uuid.uuid4().hex[:12]}"
    content = json.loads(json.dumps(source_memory["content"]))
    content["outcome"] = {
        "status": outcome,
        "details": details,
    }
    content["causalClaim"] = False

    lineage = source_memory["epistemic"]["lineage"]
    derived = create_nbg_memory(
        memory_id=f"{source_memory['memoryId']}:verified:{uuid.uuid4().hex[:8]}",
        content=content,
        origin="VERIFIED",
        confidence=source_memory["epistemic"]["confidence"],
        evidence=[*source_memory["epistemic"]["evidence"], evidence],
        root_memory_id=lineage.get("rootMemoryId") or source_memory["memoryId"],
        parent_memory_id=source_memory["memoryId"],
        transition_receipt_ids=[
            *lineage.get("transitionReceiptIds", []),
            transition_id,
        ],
        source_memory_ids=[
            *lineage.get("sourceMemoryIds", []),
            source_memory["memoryId"],
        ],
        valid_time=source_memory.get("validTime"),
        known_time=known_time or utc_now(),
        tags=source_memory.get("tags", []),
        retainable=source_memory["epistemic"]["authority"]["retainable"],
        reasoning_usable=source_memory["epistemic"]["authority"]["reasoningUsable"],
        action_authorized=False,
    )
    receipt_body = {
        "receiptType": "EPISTEMIC_PROMOTION",
        "transitionId": transition_id,
        "fromMemoryId": source_memory["memoryId"],
        "toMemoryId": derived["memoryId"],
        "fromOrigin": "INFERRED",
        "toOrigin": "VERIFIED",
        "evidenceId": evidence["evidenceId"],
        "evidenceFingerprint": evidence["evidenceFingerprint"],
        "sourceMemoryFingerprint": source_memory["recordFingerprint"],
        "derivedMemoryFingerprint": derived["recordFingerprint"],
        "knownTime": known_time or utc_now(),
        "authorityChanged": False,
    }
    receipt = {
        **receipt_body,
        "receiptFingerprint": nbg_fingerprint(receipt_body),
    }
    return derived, receipt


@dataclass(frozen=True)
class SimilarityResult:
    memory: dict[str, Any]
    similarity: float
    reliability: float
    score: float
    components: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "memoryId": self.memory["memoryId"],
            "recordFingerprint": self.memory["recordFingerprint"],
            "origin": self.memory["epistemic"]["origin"],
            "outcome": self.memory.get("content", {}).get("outcome"),
            "evidence": self.memory["epistemic"]["evidence"],
            "lineage": self.memory["epistemic"]["lineage"],
            "specialistIds": self.memory.get("content", {}).get("specialistIds", []),
            "similarity": self.similarity,
            "reliability": self.reliability,
            "score": self.score,
            "components": self.components,
        }


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9-]+", str(text).lower()))


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return 0.0 if not union else len(left & right) / len(union)


def memory_reliability(memory: dict[str, Any]) -> float:
    origin = memory.get("epistemic", {}).get("origin", "UNKNOWN")
    weight = ORIGIN_WEIGHT.get(origin, 0.0)
    outcome = memory.get("content", {}).get("outcome", {}).get("status")
    if origin == "VERIFIED" and outcome in VERIFIED_OUTCOMES:
        return 1.0
    return weight


def compare_case_to_memory(
    memory: dict[str, Any],
    *,
    symptom: str,
    domain: str,
    specialist_ids: Iterable[str] = (),
) -> SimilarityResult:
    content = memory.get("content", {})
    symptom_similarity = _jaccard(
        _tokens(symptom),
        _tokens(content.get("symptom", "")),
    )
    domain_match = 1.0 if domain and domain == content.get("domain") else 0.0
    current_specialists = set(specialist_ids)
    prior_specialists = set(content.get("specialistIds", []))
    specialist_overlap = _jaccard(current_specialists, prior_specialists)
    similarity = round(
        0.70 * symptom_similarity
        + 0.20 * domain_match
        + 0.10 * specialist_overlap,
        6,
    )
    reliability = memory_reliability(memory)
    return SimilarityResult(
        memory=memory,
        similarity=similarity,
        reliability=reliability,
        score=round(similarity * reliability, 6),
        components={
            "symptomJaccard": round(symptom_similarity, 6),
            "domainMatch": domain_match,
            "specialistOverlap": round(specialist_overlap, 6),
        },
    )


class DiagnosticMemoryStore:
    def __init__(self, root: Path):
        self.root = root
        self.records_path = root / "records.jsonl"
        self.transitions_path = root / "transitions.jsonl"
        self.admissions_path = root / "admissions.jsonl"

    @staticmethod
    def _append(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(stable_json(payload) + "\n")

    @staticmethod
    def _read(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows

    def records(self) -> list[dict[str, Any]]:
        return self._read(self.records_path)

    def _record_by_id(self, memory_id: str) -> dict[str, Any] | None:
        for record in self.records():
            if record.get("memoryId") == memory_id:
                return record
        return None

    def admit(
        self,
        memory: dict[str, Any],
        *,
        operator_label: str,
        reason: str,
        case_id: str,
    ) -> dict[str, Any]:
        if memory.get("schemaVersion") != "NBG_EPISTEMIC_1":
            raise MemoryAdmissionError("memory is not NBG_EPISTEMIC_1")
        if memory.get("epistemic", {}).get("authority", {}).get("actionAuthorized"):
            raise MemoryAdmissionError("diagnostic memory may not authorize action")
        body = {k: v for k, v in memory.items() if k != "recordFingerprint"}
        if memory.get("recordFingerprint") != nbg_fingerprint(body):
            raise MemoryAdmissionError("memory fingerprint validation failed")

        prior = self._record_by_id(memory["memoryId"])
        if prior:
            if prior["recordFingerprint"] != memory["recordFingerprint"]:
                raise MemoryConflictError(
                    f"memory ID collision with different fingerprint: {memory['memoryId']}"
                )
            return {
                "schema": "field-medic-memory-admission-v1",
                "status": "ALREADY_ADMITTED",
                "memoryId": memory["memoryId"],
                "recordFingerprint": memory["recordFingerprint"],
            }

        self._append(self.records_path, memory)
        admission_body = {
            "schema": "field-medic-memory-admission-v1",
            "admissionId": f"admission-{uuid.uuid4().hex[:12]}",
            "status": "ADMITTED",
            "caseId": case_id,
            "memoryId": memory["memoryId"],
            "recordFingerprint": memory["recordFingerprint"],
            "operatorLabel": operator_label,
            "operatorLabelSemantics": (
                "local operator label; not independently verified identity"
            ),
            "reason": reason,
            "knownTime": utc_now(),
            "actionAuthorized": False,
        }
        admission = {
            **admission_body,
            "admissionFingerprint": nbg_fingerprint(admission_body),
        }
        self._append(self.admissions_path, admission)
        return admission

    def append_transition(self, receipt: dict[str, Any]) -> None:
        self._append(self.transitions_path, receipt)

    def query(
        self,
        *,
        symptom: str,
        domain: str,
        specialist_ids: Iterable[str] = (),
        limit: int = 5,
        minimum_score: float = 0.05,
    ) -> list[SimilarityResult]:
        results = [
            compare_case_to_memory(
                memory,
                symptom=symptom,
                domain=domain,
                specialist_ids=specialist_ids,
            )
            for memory in self.records()
            if memory.get("epistemic", {}).get("authority", {}).get(
                "reasoningUsable", False
            )
        ]
        results = [item for item in results if item.score >= minimum_score]
        results.sort(
            key=lambda item: (
                -item.score,
                -item.reliability,
                item.memory["memoryId"],
            )
        )
        return results[:limit]

    def routing_hints(
        self,
        *,
        symptom: str,
        domain: str,
        specialist_ids: Iterable[str] = (),
        limit: int = 5,
    ) -> dict[str, Any]:
        matches = self.query(
            symptom=symptom,
            domain=domain,
            specialist_ids=specialist_ids,
            limit=limit,
        )
        scores: dict[str, float] = {}
        support: dict[str, list[str]] = {}
        for match in matches:
            for specialist in match.memory.get("content", {}).get(
                "specialistIds", []
            ):
                scores[specialist] = scores.get(specialist, 0.0) + match.score
                support.setdefault(specialist, []).append(
                    match.memory["memoryId"]
                )
        ranked = [
            {
                "specialistId": specialist,
                "score": round(score, 6),
                "supportingMemoryIds": support[specialist],
            }
            for specialist, score in scores.items()
        ]
        ranked.sort(key=lambda item: (-item["score"], item["specialistId"]))
        return {
            "schema": "field-medic-memory-routing-v1",
            "policy": "deterministic-provenance-preserving-case-similarity",
            "matches": [item.to_dict() for item in matches],
            "specialistHints": ranked,
            "authorityCeiling": "route-only",
            "causalClaim": False,
        }

    def stats(self) -> dict[str, Any]:
        records = self.records()
        origins: dict[str, int] = {}
        outcomes: dict[str, int] = {}
        for memory in records:
            origin = memory.get("epistemic", {}).get("origin", "UNKNOWN")
            origins[origin] = origins.get(origin, 0) + 1
            outcome = memory.get("content", {}).get("outcome", {}).get(
                "status", "UNKNOWN"
            )
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
        return {
            "records": len(records),
            "origins": origins,
            "outcomes": outcomes,
            "transitions": len(self._read(self.transitions_path)),
            "admissions": len(self._read(self.admissions_path)),
        }


def verified_outcome_weight(outcome: str) -> float:
    if outcome not in VALID_OUTCOMES:
        raise ValueError(f"unsupported diagnostic outcome: {outcome}")
    return 1.0 if outcome in VERIFIED_OUTCOMES else ORIGIN_WEIGHT["INFERRED"]
