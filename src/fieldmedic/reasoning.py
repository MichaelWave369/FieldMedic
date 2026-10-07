from __future__ import annotations

from typing import Any

from .local_models import LocalModel, choose_model


def plan_reasoning(
    *,
    domain: str,
    correlation: dict[str, Any],
    specialist_plan: dict[str, Any],
    local_models: list[LocalModel],
) -> dict[str, Any]:
    contradictions = len(correlation.get("contradictions", []))
    tensions = len(correlation.get("diagnostic_tensions", []))
    source_count = int(correlation.get("source_count", 0))

    if source_count == 0:
        tier = "deterministic"
        reason = "no source evidence is available; do not spend model compute on speculation"
    elif domain == "unknown" or contradictions:
        tier = "specialist"
        reason = "uncertain or contradictory evidence requires specialist reasoning"
    elif domain == "mixed" or tensions:
        tier = "specialist"
        reason = "cross-domain evidence requires specialist synthesis"
    else:
        tier = "utility"
        reason = "single-domain evidence can start with the cheapest adequate local model"

    selected = choose_model(local_models, tier)
    frontier_triggers: list[str] = []
    if contradictions:
        frontier_triggers.append("contradictions remain after fresh measurement")
    if domain == "unknown":
        frontier_triggers.append("specialists remain unable to classify the failure")
    if domain == "mixed":
        frontier_triggers.append("local specialist synthesis remains unresolved")

    return {
        "schema": "field-medic-reasoning-plan-v1",
        "policy": "cheap-local-first-sparse-escalation",
        "requested_tier": tier,
        "selected_local_model": selected.to_dict() if selected else None,
        "specialist_ids": specialist_plan.get("specialist_ids", []),
        "reason": reason,
        "frontier": {
            "invoked": False,
            "eligible_now": False,
            "eligible_only_after": frontier_triggers,
            "rule": "frontier reasoning is never first-line and requires unresolved local specialist work",
        },
        "authority_ceiling": "infer",
    }
