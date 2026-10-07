from __future__ import annotations

from typing import Any


class SynthesisValidationError(ValueError):
    pass


def _evidence_id_from_event(event_id: str) -> str:
    marker = ":event:"
    return event_id.split(marker, 1)[0] if marker in event_id else event_id


def _pair_refs(pair: dict[str, Any]) -> list[str]:
    refs = [
        _evidence_id_from_event(str(pair.get("left_event_id", ""))),
        _evidence_id_from_event(str(pair.get("right_event_id", ""))),
    ]
    return list(dict.fromkeys(item for item in refs if item))


def build_synthesis(
    *,
    case_id: str,
    symptom: str,
    domain: str,
    correlation: dict[str, Any],
    correlation_evidence_id: str,
    specialist_plan: dict[str, Any],
    reasoning_plan: dict[str, Any],
) -> dict[str, Any]:
    claims: list[dict[str, Any]] = []
    contradictions = correlation.get("contradictions", [])
    tensions = correlation.get("diagnostic_tensions", [])
    pairs = correlation.get("cross_source_pairs", [])

    if contradictions:
        refs = list(dict.fromkeys(ref for item in contradictions for ref in _pair_refs(item)))
        claims.append({
            "kind": "contradiction",
            "text": f"{len(contradictions)} same-subject cross-source contradiction(s) require re-measurement before repair.",
            "evidence_ids": refs or [correlation_evidence_id],
            "causal_claim": False,
        })
    if tensions:
        refs = list(dict.fromkeys(ref for item in tensions for ref in _pair_refs(item)))
        claims.append({
            "kind": "diagnostic-tension",
            "text": f"{len(tensions)} cross-source diagnostic tension(s) were observed inside the bounded correlation window.",
            "evidence_ids": refs or [correlation_evidence_id],
            "causal_claim": False,
        })
    if pairs and not contradictions and not tensions:
        refs = list(dict.fromkeys(ref for item in pairs for ref in _pair_refs(item)))
        claims.append({
            "kind": "temporal-association",
            "text": f"{len(pairs)} cross-source event pair(s) co-occurred inside the bounded time window.",
            "evidence_ids": refs or [correlation_evidence_id],
            "causal_claim": False,
        })
    if not claims:
        claims.append({
            "kind": "insufficient-correlation",
            "text": "No strong cross-source correlation claim is supported by the current bounded evidence.",
            "evidence_ids": [correlation_evidence_id],
            "causal_claim": False,
        })

    receipt = {
        "schema": "field-medic-synthesis-v1",
        "case_id": case_id,
        "symptom": symptom,
        "domain": domain,
        "summary": claims[0]["text"],
        "claims": claims,
        "specialist_ids": specialist_plan.get("specialist_ids", []),
        "reasoning": reasoning_plan,
        "uncertainties": list(correlation.get("limits", [])),
        "causal_claim": False,
        "authority_ceiling": "infer",
    }
    validate_synthesis(
        receipt,
        available_evidence_ids=set(correlation.get("evidence_ids", []) + [correlation_evidence_id]),
    )
    return receipt


def validate_synthesis(receipt: dict[str, Any], *, available_evidence_ids: set[str]) -> None:
    required = {
        "schema", "case_id", "symptom", "domain", "summary", "claims",
        "specialist_ids", "reasoning", "uncertainties", "causal_claim", "authority_ceiling",
    }
    missing = sorted(required - set(receipt))
    if missing:
        raise SynthesisValidationError(f"synthesis is missing required fields: {missing}")
    if receipt.get("schema") != "field-medic-synthesis-v1":
        raise SynthesisValidationError("unexpected synthesis schema")
    if receipt.get("authority_ceiling") != "infer":
        raise SynthesisValidationError("synthesis authority ceiling must remain infer")
    if receipt.get("causal_claim") is not False:
        raise SynthesisValidationError("synthesis receipt must keep causal_claim=false")
    claims = receipt.get("claims")
    if not isinstance(claims, list) or not claims:
        raise SynthesisValidationError("synthesis must include at least one claim")
    for claim in claims:
        refs = claim.get("evidence_ids")
        if not isinstance(refs, list) or not refs:
            raise SynthesisValidationError("every synthesis claim must cite evidence IDs")
        unknown = [item for item in refs if item not in available_evidence_ids]
        if unknown:
            raise SynthesisValidationError(f"claim cites unknown evidence IDs: {unknown}")
        if claim.get("causal_claim") is not False:
            raise SynthesisValidationError("individual synthesis claims must keep causal_claim=false")
