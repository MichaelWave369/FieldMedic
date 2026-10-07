from __future__ import annotations

import json
from typing import Any
from urllib.request import Request, urlopen

from .synthesis import validate_synthesis, SynthesisValidationError


class LocalReasoningError(RuntimeError):
    pass


def ollama_synthesis(
    *,
    model: str,
    base_receipt: dict[str, Any],
    available_evidence_ids: set[str],
    timeout: float = 45.0,
) -> dict[str, Any]:
    prompt = {
        "instruction": (
            "Refine the diagnostic synthesis using only the supplied receipt. "
            "Return JSON with schema=field-medic-synthesis-v1, the same case_id, "
            "symptom and domain, a concise summary, claims with explicit evidence_ids, "
            "uncertainties, causal_claim=false, and authority_ceiling=infer. "
            "Do not invent evidence IDs and do not assert causation."
        ),
        "receipt": base_receipt,
        "allowed_evidence_ids": sorted(available_evidence_ids),
    }
    body = json.dumps({
        "model": model,
        "prompt": json.dumps(prompt),
        "format": "json",
        "stream": False,
    }).encode("utf-8")
    req = Request(
        "http://127.0.0.1:11434/api/generate",
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as response:
            outer = json.loads(response.read().decode("utf-8"))
        candidate = json.loads(outer.get("response", ""))
    except Exception as exc:
        raise LocalReasoningError(f"local Ollama reasoning failed: {exc}") from exc
    if not isinstance(candidate, dict):
        raise LocalReasoningError("local model synthesis root must be an object")

    candidate["schema"] = "field-medic-synthesis-v1"
    candidate["case_id"] = base_receipt["case_id"]
    candidate["symptom"] = base_receipt["symptom"]
    candidate["domain"] = base_receipt["domain"]
    candidate["specialist_ids"] = base_receipt["specialist_ids"]
    candidate["reasoning"] = base_receipt["reasoning"]
    candidate["causal_claim"] = False
    candidate["authority_ceiling"] = "infer"

    try:
        validate_synthesis(candidate, available_evidence_ids=available_evidence_ids)
    except SynthesisValidationError as exc:
        raise LocalReasoningError(f"local model synthesis rejected: {exc}") from exc
    return candidate
