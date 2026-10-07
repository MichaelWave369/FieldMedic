from __future__ import annotations

from pathlib import Path
from typing import Any

from .adapters.drivemedic import DriveMedicAdapter
from .adapters.netmedic import NetMedicAdapter
from .experiments import ExperimentGate, ExperimentProposal, save_json
from .hashutil import sha256_json


class GovernedExperimentRunner:
    def __init__(
        self,
        *,
        home: Path,
        drivemedic: str | None,
        netmedic: str,
    ):
        self.home = home
        self.drive = DriveMedicAdapter(drivemedic) if drivemedic else None
        self.net = NetMedicAdapter(netmedic)
        self.gate = ExperimentGate()

    def _dir(self, proposal: ExperimentProposal) -> Path:
        return self.home / "cases" / proposal.case_id / "experiments" / proposal.proposal_id

    def freeze(self, proposal: ExperimentProposal, approval: dict[str, Any]) -> dict[str, Any]:
        self.gate.require(
            proposal=proposal,
            approval=approval,
            scope="netmedic.protocol.freeze",
        )
        receipt = self.net.freeze_protocol(proposal)
        record = {
            "schema": "field-medic-experiment-freeze-v1",
            "proposal_id": proposal.proposal_id,
            "proposal_sha256": proposal.sha256,
            "approval_id": approval["approval_id"],
            "netmedic_receipt": receipt,
            "receipt_sha256": sha256_json(receipt),
            "causal_claim": False,
            "repair_authority": False,
        }
        save_json(self._dir(proposal) / "freeze.json", record)
        return record

    def capture(
        self,
        proposal: ExperimentProposal,
        approval: dict[str, Any],
        *,
        protocol_fingerprint: str,
    ) -> dict[str, Any]:
        self.gate.require(
            proposal=proposal,
            approval=approval,
            scope="netmedic.protocol.capture",
            require_physical_confirmations=True,
        )

        before = self.drive.status() if self.drive else None
        confirm = approval["confirmations"]
        preflight = self.net.preflight_protocol(
            case=proposal.netmedic_case,
            protocol_fingerprint=protocol_fingerprint,
            control_keys=[key for key, _ in proposal.controls],
            confirm_arm=bool(confirm["arm"]),
            confirm_machine_stable=bool(confirm["machine_stable"]),
            confirm_test_context=bool(confirm["test_context"]),
        )
        execution = self.net.execute_protocol(
            case=proposal.netmedic_case,
            protocol_fingerprint=protocol_fingerprint,
            preflight_receipt=preflight["_local_receipt_path"],
        )
        after = self.drive.status() if self.drive else None

        public_preflight = {k: v for k, v in preflight.items() if k != "_local_receipt_path"}
        record = {
            "schema": "field-medic-experiment-capture-v1",
            "proposal_id": proposal.proposal_id,
            "proposal_sha256": proposal.sha256,
            "approval_id": approval["approval_id"],
            "protocol_fingerprint": protocol_fingerprint,
            "host_before": before,
            "host_after": after,
            "netmedic_preflight": public_preflight,
            "netmedic_execution": execution,
            "host_before_sha256": sha256_json(before) if before is not None else None,
            "host_after_sha256": sha256_json(after) if after is not None else None,
            "causal_claim": False,
            "repair_authority": False,
        }
        directory = self._dir(proposal) / "captures"
        directory.mkdir(parents=True, exist_ok=True)
        index = len(list(directory.glob("capture-*.json"))) + 1
        save_json(directory / f"capture-{index:03d}.json", record)
        return record

    def matched(
        self,
        proposal: ExperimentProposal,
        approval: dict[str, Any],
        *,
        protocol_fingerprint: str,
    ) -> dict[str, Any]:
        self.gate.require(
            proposal=proposal,
            approval=approval,
            scope="netmedic.protocol.matched",
        )
        receipt = self.net.matched_protocol(
            case=proposal.netmedic_case,
            protocol_fingerprint=protocol_fingerprint,
        )
        record = {
            "schema": "field-medic-experiment-matched-v1",
            "proposal_id": proposal.proposal_id,
            "proposal_sha256": proposal.sha256,
            "approval_id": approval["approval_id"],
            "protocol_fingerprint": protocol_fingerprint,
            "netmedic_receipt": receipt,
            "receipt_sha256": sha256_json(receipt),
            "causal_claim": False,
            "claim_boundary": "matched association does not establish causation",
            "repair_authority": False,
        }
        save_json(self._dir(proposal) / "matched.json", record)
        return record
