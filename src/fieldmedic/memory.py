from __future__ import annotations
from typing import Any


def nbg_projection(*, case_id: str, symptom: str, route: dict, evidence_ids: list[str]) -> dict[str, Any]:
    """Creates a portable candidate for later NBG admission. It does not write to NBG."""
    return {
        "schema": "field-medic-nbg-candidate-v1",
        "case_id": case_id,
        "bubbles": [
            {"id": f"case:{case_id}", "kind": "case"},
            {"id": f"symptom:{case_id}", "kind": "symptom", "text": symptom},
            {"id": f"domain:{route['domain']}", "kind": "diagnostic-domain"},
        ],
        "edges": [
            {"from": f"case:{case_id}", "to": f"symptom:{case_id}", "relation": "REPORTS"},
            {"from": f"case:{case_id}", "to": f"domain:{route['domain']}", "relation": "ROUTED_TO"},
        ],
        "evidence_refs": evidence_ids,
        "admission": "CANDIDATE_ONLY",
        "causal_claim": False,
    }
