from __future__ import annotations
import uuid
from typing import Any
from .hashutil import sha256_json
from .models import EvidenceEnvelope, ClaimClass, Source, utc_now


def wrap_evidence(*, case_id: str, source: Source, category: str, summary: str,
                  payload: Any, source_version: str | None = None,
                  observed_at: str | None = None,
                  claim_class: ClaimClass = ClaimClass.OBSERVATION,
                  confidence: float | None = None,
                  provenance: dict[str, Any] | None = None) -> EvidenceEnvelope:
    digest = sha256_json(payload)
    return EvidenceEnvelope(
        schema="field-medic-evidence-v1",
        evidence_id=f"ev-{uuid.uuid4().hex[:16]}",
        case_id=case_id,
        source=source.value,
        source_version=source_version,
        observed_at=observed_at or utc_now(),
        ingested_at=utc_now(),
        category=category,
        claim_class=claim_class.value,
        summary=summary,
        payload_sha256=digest,
        payload=payload,
        confidence=confidence,
        causal_claim=False,
        provenance=provenance or {},
    )
