from __future__ import annotations
import uuid
from pathlib import Path
from typing import Any
from .adapters.drivemedic import DriveMedicAdapter
from .adapters.netmedic import NetMedicAdapter
from .envelope import wrap_evidence
from .ledger import EvidenceLedger
from .models import Source, ActionProposal, Authority, utc_now
from .policy import RealityGate
from .router import route
from .memory import nbg_projection


class AgentMedic:
    def __init__(self, home: Path):
        self.home = home
        self.gate = RealityGate()

    def new_case_id(self) -> str:
        return f"case-{uuid.uuid4().hex[:12]}"

    def health(self, drivemedic: str | None, netmedic: str | None) -> dict[str, Any]:
        out: dict[str, Any] = {"fieldmedic": "ok", "engines": {}}
        if drivemedic:
            try:
                out["engines"]["drivemedic"] = {"ok": True, "self_check": DriveMedicAdapter(drivemedic).self_check()}
            except Exception as exc:
                out["engines"]["drivemedic"] = {"ok": False, "error": str(exc)}
        if netmedic:
            try:
                out["engines"]["netmedic"] = {"ok": True, "crypto_status": NetMedicAdapter(netmedic).crypto_status_text()}
            except Exception as exc:
                out["engines"]["netmedic"] = {"ok": False, "error": str(exc)}
        return out

    def doctor(self, symptom: str, drivemedic: str | None, netmedic: str | None,
               case_id: str | None = None) -> dict[str, Any]:
        self.gate.require(Authority.OBSERVE)
        case_id = case_id or self.new_case_id()
        decision = route(symptom)
        case_dir = self.home / "cases" / case_id
        ledger = EvidenceLedger(case_dir / "evidence.jsonl")
        evidence = []
        errors: list[dict[str, str]] = []

        if drivemedic and decision.domain in {"host", "mixed", "unknown"}:
            try:
                raw = DriveMedicAdapter(drivemedic).status()
                ev = wrap_evidence(case_id=case_id, source=Source.DRIVEMEDIC,
                    category="host.status", summary="DriveMedic host status snapshot", payload=raw,
                    provenance={"adapter": "status-json"})
                ledger.append(ev); evidence.append(ev)
            except Exception as exc:
                errors.append({"source": "drivemedic", "error": str(exc)})

        if netmedic and decision.domain in {"network", "mixed", "unknown"}:
            try:
                raw = NetMedicAdapter(netmedic).snapshot()
                ev = wrap_evidence(case_id=case_id, source=Source.NETMEDIC,
                    category="network.snapshot", summary="NetMedic privacy-safe network snapshot", payload=raw,
                    provenance={"adapter": "--report + --redact-report + --omit-raw-evidence"})
                ledger.append(ev); evidence.append(ev)
            except Exception as exc:
                errors.append({"source": "netmedic", "error": str(exc)})

        self.gate.require(Authority.INFER)
        proposal = self._next_step(case_id, decision.domain, tuple(e.evidence_id for e in evidence))
        route_dict = decision.to_dict()
        memory_candidate = nbg_projection(case_id=case_id, symptom=symptom,
                                          route=route_dict,
                                          evidence_ids=[e.evidence_id for e in evidence])
        case_dir.mkdir(parents=True, exist_ok=True)
        import json
        (case_dir / "nbg-candidate.json").write_text(json.dumps(memory_candidate, indent=2), encoding="utf-8")
        result = {
            "schema": "field-medic-case-v1",
            "case_id": case_id,
            "symptom": symptom,
            "routing": route_dict,
            "evidence": [e.to_dict() for e in evidence],
            "errors": errors,
            "proposal": proposal.to_dict(),
            "authority": {
                "agent_can": ["observe", "infer", "propose"],
                "agent_cannot": ["execute"],
            },
            "memory_candidate": memory_candidate,
        }
        (case_dir / "case.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result

    def _next_step(self, case_id: str, domain: str, evidence_ids: tuple[str, ...]) -> ActionProposal:
        self.gate.require(Authority.PROPOSE)
        if domain == "mixed":
            text = "Correlate host and network timestamps; if ambiguity remains, run a controlled NetMedic A/B path experiment."
        elif domain == "network":
            text = "Review the NetMedic snapshot; if intermittent, start a bounded watch or frozen A/B experiment before changing configuration."
        elif domain == "host":
            text = "Review DriveMedic timeline/change evidence and create a guided repair plan only after a specific incident is identified."
        else:
            text = "Collect one host status snapshot and one privacy-safe network snapshot before choosing a repair path."
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
