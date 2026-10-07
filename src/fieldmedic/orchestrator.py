from __future__ import annotations
import json
import uuid
from pathlib import Path
from typing import Any

from .adapters.drivemedic import DriveMedicAdapter
from .adapters.netmedic import NetMedicAdapter
from .brainc import BrainCRouter, BrainCRoutingError
from .correlation import correlate_evidence
from .envelope import wrap_evidence
from .experiments import suggest_experiment_template, save_json
from .ledger import EvidenceLedger
from .local_models import discover_local_models, choose_model
from .local_reasoner import ollama_synthesis, LocalReasoningError
from .models import Source, ClaimClass, ActionProposal, Authority, utc_now
from .policy import RealityGate
from .router import route
from .nbg_memory import (
    DiagnosticMemoryStore,
    case_to_inferred_memory,
    merge_specialist_hints,
)
from .reasoning import plan_reasoning
from .specialists import SPECIALISTS, plan_specialists, materialize_specialist_plan
from .synthesis import build_synthesis


class AgentMedic:
    def __init__(self, home: Path, brainc_binary: str | None = None):
        self.home = home
        self.gate = RealityGate()
        self.brainc = BrainCRouter(brainc_binary)

    def new_case_id(self) -> str:
        return f"case-{uuid.uuid4().hex[:12]}"

    def health(
        self,
        drivemedic: str | None,
        netmedic: str | None,
        *,
        discover_models: bool = True,
    ) -> dict[str, Any]:
        out: dict[str, Any] = {
            "fieldmedic": "ok",
            "engines": {},
            "brainc": {"configured": self.brainc.available},
        }
        if drivemedic:
            try:
                out["engines"]["drivemedic"] = {
                    "ok": True,
                    "self_check": DriveMedicAdapter(drivemedic).self_check(),
                }
            except Exception as exc:
                out["engines"]["drivemedic"] = {"ok": False, "error": str(exc)}
        if netmedic:
            try:
                out["engines"]["netmedic"] = {
                    "ok": True,
                    "crypto_status": NetMedicAdapter(netmedic).crypto_status_text(),
                }
            except Exception as exc:
                out["engines"]["netmedic"] = {"ok": False, "error": str(exc)}
        if discover_models:
            models = discover_local_models()
            out["local_models"] = [model.to_dict() for model in models]
        return out

    def doctor(
        self,
        symptom: str,
        drivemedic: str | None,
        netmedic: str | None,
        case_id: str | None = None,
        *,
        discover_models: bool = True,
        local_reasoning: bool = False,
        netmedic_case: str | None = None,
    ) -> dict[str, Any]:
        self.gate.require(Authority.OBSERVE)
        case_id = case_id or self.new_case_id()
        decision = route(symptom)
        case_dir = self.home / "cases" / case_id
        ledger = EvidenceLedger(case_dir / "evidence.jsonl")
        evidence = []
        errors: list[dict[str, str]] = []

        if drivemedic and decision.domain in {"host", "mixed", "unknown"}:
            drive = DriveMedicAdapter(drivemedic)
            try:
                raw = drive.status()
                ev = wrap_evidence(
                    case_id=case_id,
                    source=Source.DRIVEMEDIC,
                    category="host.status",
                    summary="DriveMedic host status snapshot",
                    payload=raw,
                    provenance={"adapter": "status-json"},
                )
                ledger.append(ev)
                evidence.append(ev)
            except Exception as exc:
                errors.append({"source": "drivemedic.status", "error": str(exc)})

            try:
                raw = drive.timeline(hours=6, max_points=720)
                ev = wrap_evidence(
                    case_id=case_id,
                    source=Source.DRIVEMEDIC,
                    category="host.timeline",
                    summary="DriveMedic bounded six-hour timeline",
                    payload=raw,
                    provenance={
                        "adapter": "timeline-json",
                        "hours": 6,
                        "max_points": 720,
                    },
                )
                ledger.append(ev)
                evidence.append(ev)
            except Exception as exc:
                errors.append({"source": "drivemedic.timeline", "error": str(exc)})

        if netmedic and decision.domain in {"network", "mixed", "unknown"}:
            try:
                raw = NetMedicAdapter(netmedic).snapshot()
                ev = wrap_evidence(
                    case_id=case_id,
                    source=Source.NETMEDIC,
                    category="network.snapshot",
                    summary="NetMedic privacy-safe network snapshot",
                    payload=raw,
                    provenance={
                        "adapter": "--report + --redact-report + --omit-raw-evidence"
                    },
                )
                ledger.append(ev)
                evidence.append(ev)
            except Exception as exc:
                errors.append({"source": "netmedic", "error": str(exc)})

        self.gate.require(Authority.INFER)
        correlation = correlate_evidence(evidence, window_seconds=30)
        correlation_evidence = wrap_evidence(
            case_id=case_id,
            source=Source.AGENT_MEDIC,
            category="case.correlation",
            summary="Deterministic cross-source temporal correlation",
            payload=correlation,
            claim_class=ClaimClass.INFERENCE,
            provenance={
                "engine": "deterministic-correlation-v1",
                "input_evidence_ids": [item.evidence_id for item in evidence],
            },
        )
        ledger.append(correlation_evidence)
        evidence.append(correlation_evidence)

        specialist_plan = plan_specialists(symptom, decision.domain, correlation)
        memory_store = DiagnosticMemoryStore(self.home / "memory" / "nbg")
        try:
            memory_routing = memory_store.routing_hints(
                symptom=symptom,
                domain=decision.domain,
                specialist_ids=specialist_plan["specialist_ids"],
            )
            merged_ids, memory_hints = merge_specialist_hints(
                specialist_plan["specialist_ids"],
                memory_routing,
                known_ids=SPECIALISTS,
            )
            if memory_hints:
                specialist_plan = materialize_specialist_plan(
                    merged_ids,
                    reasons=[
                        *specialist_plan.get("reasons", []),
                        *[
                            "nbg-memory: prior provenance-preserving case similarity supports "
                            + item
                            for item in memory_hints
                        ],
                    ],
                    source="deterministic+nbg-memory",
                )
        except Exception as exc:
            memory_routing = {
                "schema": "field-medic-memory-routing-v1",
                "policy": "deterministic-provenance-preserving-case-similarity",
                "matches": [],
                "specialistHints": [],
                "routingLineageCount": 0,
                "authorityCeiling": "route-only",
                "causalClaim": False,
                "status": "PROVENANCE_INVALID_OR_UNAVAILABLE",
                "error": str(exc),
            }
            errors.append({"source": "nbg-memory", "error": str(exc)})

        local_models = discover_local_models() if discover_models else []
        reasoning_plan = plan_reasoning(
            domain=decision.domain,
            correlation=correlation,
            specialist_plan=specialist_plan,
            local_models=local_models,
        )

        brainc_result = None
        if self.brainc.available and correlation.get("source_count", 0) > 0:
            request = {
                "schema": "field-medic-brainc-routing-request-v1",
                "case_id": case_id,
                "symptom": symptom,
                "domain": decision.domain,
                "deterministic_specialist_ids": specialist_plan["specialist_ids"],
                "correlation": {
                    "source_count": correlation.get("source_count", 0),
                    "cross_source_pair_count": len(correlation.get("cross_source_pairs", [])),
                    "contradiction_count": len(correlation.get("contradictions", [])),
                    "diagnostic_tension_count": len(correlation.get("diagnostic_tensions", [])),
                    "causal_claim": False,
                },
                "local_models": [model.to_dict() for model in local_models],
                "constraints": {
                    "allowed_reasoning_tiers": ["deterministic", "utility", "specialist"],
                    "frontier_allowed": False,
                    "authority_ceiling": "infer",
                },
            }
            try:
                brainc_result = self.brainc.route(request, frontier_allowed=False)
                brainc_ids = list(dict.fromkeys([
                    *specialist_plan["specialist_ids"],
                    *brainc_result["specialist_ids"],
                ]))
                specialist_plan = materialize_specialist_plan(
                    brainc_ids,
                    reasons=[
                        *specialist_plan.get("reasons", []),
                        *brainc_result["reasons"],
                    ],
                    source="deterministic+memory+brainc",
                )
                requested_tier = brainc_result["reasoning_tier"]
                selected = choose_model(local_models, requested_tier)
                reasoning_plan = {
                    **reasoning_plan,
                    "requested_tier": requested_tier,
                    "selected_local_model": selected.to_dict() if selected else None,
                    "specialist_ids": specialist_plan["specialist_ids"],
                    "routing_source": "brainc",
                    "brainc_escalate": brainc_result["escalate"],
                }
            except BrainCRoutingError as exc:
                errors.append({"source": "brainc", "error": str(exc)})

        synthesis = build_synthesis(
            case_id=case_id,
            symptom=symptom,
            domain=decision.domain,
            correlation=correlation,
            correlation_evidence_id=correlation_evidence.evidence_id,
            specialist_plan=specialist_plan,
            reasoning_plan=reasoning_plan,
        )

        local_reasoning_status = {
            "requested": bool(local_reasoning),
            "invoked": False,
            "model": None,
            "fallback": None,
        }
        selected_model = reasoning_plan.get("selected_local_model")
        if local_reasoning and selected_model:
            local_reasoning_status["model"] = selected_model["name"]
            available_ids = set(correlation.get("evidence_ids", []))
            available_ids.add(correlation_evidence.evidence_id)
            try:
                synthesis = ollama_synthesis(
                    model=selected_model["name"],
                    base_receipt=synthesis,
                    available_evidence_ids=available_ids,
                )
                local_reasoning_status["invoked"] = True
            except LocalReasoningError as exc:
                local_reasoning_status["fallback"] = "deterministic-synthesis"
                errors.append({"source": "local_reasoner", "error": str(exc)})
        elif local_reasoning:
            local_reasoning_status["fallback"] = "no-eligible-local-model"

        synthesis_evidence = wrap_evidence(
            case_id=case_id,
            source=Source.AGENT_MEDIC,
            category="case.synthesis",
            summary=synthesis["summary"],
            payload=synthesis,
            claim_class=ClaimClass.INFERENCE,
            provenance={
                "engine": (
                    "ollama-local-synthesis-v1"
                    if local_reasoning_status["invoked"]
                    else "deterministic-synthesis-v1"
                ),
                "input_evidence_ids": correlation.get("evidence_ids", [])
                + [correlation_evidence.evidence_id],
                "specialist_ids": specialist_plan["specialist_ids"],
            },
        )
        ledger.append(synthesis_evidence)
        evidence.append(synthesis_evidence)

        experiment_proposal = suggest_experiment_template(
            symptom=symptom,
            case_id=case_id,
            netmedic_case=netmedic_case,
            evidence_ids=correlation.get("evidence_ids", []) + [
                correlation_evidence.evidence_id,
                synthesis_evidence.evidence_id,
            ],
        )
        experiment_record = None
        if experiment_proposal is not None:
            proposal_path = (
                case_dir
                / "experiment-proposals"
                / f"{experiment_proposal.proposal_id}.json"
            )
            save_json(proposal_path, experiment_proposal.to_dict())
            experiment_record = {
                "proposal": experiment_proposal.to_dict(),
                "proposal_sha256": experiment_proposal.sha256,
                "path": str(proposal_path),
                "status": "PROPOSED_NOT_AUTHORIZED",
            }

        proposal = self._next_step(
            case_id,
            decision.domain,
            tuple(item.evidence_id for item in evidence),
            correlation,
        )
        route_dict = decision.to_dict()
        case_dir.mkdir(parents=True, exist_ok=True)
        result = {
            "schema": "field-medic-case-v1",
            "case_id": case_id,
            "symptom": symptom,
            "routing": route_dict,
            "specialist_plan": specialist_plan,
            "memory_routing": memory_routing,
            "reasoning_plan": reasoning_plan,
            "brainc": {
                "configured": self.brainc.available,
                "result": brainc_result,
            },
            "local_models": [model.to_dict() for model in local_models],
            "local_reasoning": local_reasoning_status,
            "evidence": [item.to_dict() for item in evidence],
            "correlation": correlation,
            "synthesis": synthesis,
            "experiment_proposal": experiment_record,
            "errors": errors,
            "proposal": proposal.to_dict(),
            "authority": {
                "agent_can": ["observe", "infer", "propose"],
                "agent_cannot": ["execute"],
            },
        }
        candidate_memory = case_to_inferred_memory(result)
        memory_candidate = {
            "schema": "field-medic-nbg-candidate-v2",
            "case_id": case_id,
            "admission": "CANDIDATE_ONLY",
            "memory": candidate_memory,
            "causal_claim": False,
            "action_authorized": False,
        }
        result["memory_candidate"] = memory_candidate
        (case_dir / "nbg-candidate.json").write_text(
            json.dumps(memory_candidate, indent=2), encoding="utf-8"
        )
        (case_dir / "case.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8"
        )
        return result

    def _next_step(
        self,
        case_id: str,
        domain: str,
        evidence_ids: tuple[str, ...],
        correlation: dict[str, Any] | None = None,
    ) -> ActionProposal:
        self.gate.require(Authority.PROPOSE)
        correlation = correlation or {}
        contradictions = len(correlation.get("contradictions", []))
        tensions = len(correlation.get("diagnostic_tensions", []))
        pairs = len(correlation.get("cross_source_pairs", []))

        if contradictions:
            text = (
                "Resolve contradictory observations for the same subject before any repair. "
                "Collect a fresh bounded snapshot from both engines."
            )
        elif domain == "mixed" and tensions:
            text = (
                "Review the cross-source diagnostic tension; preserve both observations and "
                "run a controlled NetMedic A/B path experiment before changing configuration."
            )
        elif domain == "mixed" and pairs:
            text = (
                "Review the correlated host/network event window; if ambiguity remains, "
                "run a controlled NetMedic A/B path experiment."
            )
        elif domain == "mixed":
            text = (
                "No strong cross-source time window was found. Collect a focused incident "
                "window from both engines before proposing a repair."
            )
        elif domain == "network":
            text = (
                "Review the NetMedic snapshot; if intermittent, start a bounded watch or "
                "frozen A/B experiment before changing configuration."
            )
        elif domain == "host":
            text = (
                "Review DriveMedic timeline/change evidence and create a guided repair plan "
                "only after a specific incident is identified."
            )
        else:
            text = (
                "Collect one host timeline and one privacy-safe network snapshot before "
                "choosing a repair path."
            )

        return ActionProposal(
            action_id=f"proposal-{uuid.uuid4().hex[:12]}",
            case_id=case_id,
            proposed_at=utc_now(),
            action_type="diagnostic-next-step",
            description=text,
            requested_authority=Authority.PROPOSE.value,
            reversible=True,
            evidence_ids=evidence_ids,
        )
