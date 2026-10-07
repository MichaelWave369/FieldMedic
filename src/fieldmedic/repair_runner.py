from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .adapters.drivemedic import DriveMedicAdapter
from .adapters.netmedic import NetMedicAdapter
from .envelope import wrap_evidence
from .hashutil import sha256_json
from .ledger import EvidenceLedger
from .models import ClaimClass, Source
from .repair_executors import (
    RepairBackend,
    RepairExecutorError,
    get_executor,
)
from .repair_governance import (
    RepairDenied,
    RepairGate,
    RepairProposal,
    validate_case_for_repair,
    save_json,
)


class RepairRunner:
    def __init__(
        self,
        *,
        home: Path,
        drivemedic: str | None,
        netmedic: str | None,
        backend: RepairBackend | None = None,
    ):
        self.home = home
        self.drive = DriveMedicAdapter(drivemedic) if drivemedic else None
        self.net = NetMedicAdapter(netmedic) if netmedic else None
        self.backend = backend
        self.gate = RepairGate()

    def _case_dir(self, case_id: str) -> Path:
        return self.home / "cases" / case_id

    def _case(self, case_id: str) -> dict[str, Any]:
        path = self._case_dir(case_id) / "case.json"
        if not path.exists():
            raise RepairDenied(f"FieldMedic case not found: {path}")
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise RepairDenied("FieldMedic case root must be an object")
        return value

    def _ledger(self, case_id: str) -> EvidenceLedger:
        return EvidenceLedger(self._case_dir(case_id) / "evidence.jsonl")

    def _executor(self, action_key: str):
        return get_executor(action_key, self.backend)

    def _require_verifiers(self) -> None:
        if self.drive is None or self.net is None:
            raise RepairDenied(
                "bounded repair execution requires both DriveMedic and NetMedic "
                "for independent before/after verification"
            )

    def _capture_verifiers(
        self,
        *,
        case_id: str,
        stage: str,
        proposal: RepairProposal,
    ) -> dict[str, Any]:
        self._require_verifiers()
        assert self.drive is not None
        assert self.net is not None
        drive_payload = self.drive.status()
        net_payload = self.net.snapshot()

        drive_evidence = wrap_evidence(
            case_id=case_id,
            source=Source.DRIVEMEDIC,
            category=f"repair.{stage}.host",
            summary=f"DriveMedic {stage} repair verification snapshot",
            payload=drive_payload,
            claim_class=ClaimClass.OBSERVATION,
            provenance={
                "repair_proposal_id": proposal.proposal_id,
                "action_key": proposal.action_key,
                "stage": stage,
            },
        )
        net_evidence = wrap_evidence(
            case_id=case_id,
            source=Source.NETMEDIC,
            category=f"repair.{stage}.network",
            summary=f"NetMedic {stage} repair verification snapshot",
            payload=net_payload,
            claim_class=ClaimClass.OBSERVATION,
            provenance={
                "repair_proposal_id": proposal.proposal_id,
                "action_key": proposal.action_key,
                "stage": stage,
            },
        )
        ledger = self._ledger(case_id)
        ledger.append(drive_evidence)
        ledger.append(net_evidence)
        return {
            "drivemedic_evidence": drive_evidence.to_dict(),
            "netmedic_evidence": net_evidence.to_dict(),
        }

    @staticmethod
    def _state_hash(state: dict[str, Any]) -> str:
        return sha256_json(state)

    def _rollback_exact(
        self,
        *,
        proposal: RepairProposal,
        before: dict[str, Any],
        expected_applied: dict[str, Any],
        executor,
    ) -> dict[str, Any]:
        current = executor.inspect(proposal.params)
        if executor.state_matches(current, before):
            return {
                "status": "ALREADY_AT_ROLLBACK_STATE",
                "state": current,
                "state_sha256": self._state_hash(current),
            }
        if not executor.state_matches(current, expected_applied):
            raise RepairDenied(
                "rollback denied because target state drifted after execution; "
                "refusing to overwrite an unknown later change"
            )
        restored = executor.rollback(proposal.params, before)
        if not executor.state_matches(restored, before):
            raise RepairExecutorError(
                "rollback command completed but exact rollback state was not restored"
            )
        return {
            "status": "ROLLED_BACK",
            "state": restored,
            "state_sha256": self._state_hash(restored),
        }

    def execute(
        self,
        proposal: RepairProposal,
        preflight: dict[str, Any],
        grant: dict[str, Any],
    ) -> dict[str, Any]:
        case = self._case(proposal.case_id)
        self.gate.require_execute(
            proposal=proposal,
            preflight=preflight,
            grant=grant,
            case=case,
        )
        self._require_verifiers()
        validate_case_for_repair(
            case,
            action_key=proposal.action_key,
            evidence_ids=proposal.evidence_ids,
        )

        executor = self._executor(proposal.action_key)
        current = executor.inspect(proposal.params)
        if self._state_hash(current) != preflight.get("state_before_sha256"):
            raise RepairDenied(
                "repair precondition state changed after preflight; prepare again"
            )

        baseline = self._capture_verifiers(
            case_id=proposal.case_id,
            stage="baseline",
            proposal=proposal,
        )

        before = preflight["state_before"]
        expected = preflight["expected_applied_state"]
        status = "EXECUTED_PENDING_OUTCOME_VERIFICATION"
        error: str | None = None
        rollback: dict[str, Any] | None = None

        try:
            applied = executor.apply(proposal.params, before)
            if not executor.state_matches(applied, expected):
                error = "typed repair postcondition did not match expected applied state"
                rollback = self._rollback_exact(
                    proposal=proposal,
                    before=before,
                    expected_applied=expected,
                    executor=executor,
                )
                status = "ROLLED_BACK_POSTCONDITION_FAILED"
                post = None
            else:
                try:
                    post = self._capture_verifiers(
                        case_id=proposal.case_id,
                        stage="postaction",
                        proposal=proposal,
                    )
                except Exception as exc:
                    error = f"independent post-action verification capture failed: {exc}"
                    rollback = self._rollback_exact(
                        proposal=proposal,
                        before=before,
                        expected_applied=expected,
                        executor=executor,
                    )
                    status = "ROLLED_BACK_VERIFICATION_CAPTURE_FAILED"
                    post = None
        except Exception as exc:
            if isinstance(exc, RepairDenied):
                raise
            error = str(exc)
            current_after_error = executor.inspect(proposal.params)
            if executor.state_matches(current_after_error, expected):
                rollback = self._rollback_exact(
                    proposal=proposal,
                    before=before,
                    expected_applied=expected,
                    executor=executor,
                )
                status = "ROLLED_BACK_EXECUTOR_ERROR"
                applied = current_after_error
            elif executor.state_matches(current_after_error, before):
                status = "EXECUTOR_FAILED_NO_STATE_CHANGE"
                applied = current_after_error
            else:
                raise RepairExecutorError(
                    "repair executor failed and target entered an unknown state; "
                    "automatic rollback refused because exact applied-state identity "
                    "could not be established"
                ) from exc
            post = None

        record = {
            "schema": "field-medic-repair-execution-v1",
            "case_id": proposal.case_id,
            "proposal": proposal.to_dict(),
            "proposal_sha256": proposal.sha256,
            "preflight": preflight,
            "grant": grant,
            "action_key": proposal.action_key,
            "params": proposal.params,
            "state_before": before,
            "state_before_sha256": self._state_hash(before),
            "expected_applied_state": expected,
            "expected_applied_state_sha256": self._state_hash(expected),
            "state_after_apply": applied,
            "state_after_apply_sha256": self._state_hash(applied),
            "baseline_verification": baseline,
            "postaction_verification": post,
            "rollback": rollback,
            "status": status,
            "error": error,
            "outcome_claim": "UNCLASSIFIED",
            "causal_claim": False,
            "generic_shell_used": False,
        }
        execution_evidence = wrap_evidence(
            case_id=proposal.case_id,
            source=Source.AGENT_MEDIC,
            category="repair.execution",
            summary=f"Bounded repair transaction: {status}",
            payload=record,
            claim_class=ClaimClass.GOVERNANCE,
            provenance={
                "proposal_sha256": proposal.sha256,
                "preflight_sha256": preflight["preflight_sha256"],
                "grant_sha256": grant["grant_sha256"],
                "action_key": proposal.action_key,
            },
        )
        self._ledger(proposal.case_id).append(execution_evidence)
        record["execution_evidence_id"] = execution_evidence.evidence_id

        directory = (
            self._case_dir(proposal.case_id)
            / "repairs"
            / proposal.proposal_id
        )
        save_json(directory / "execution.json", record)
        return record

    def verify(self, execution: dict[str, Any]) -> dict[str, Any]:
        if execution.get("schema") != "field-medic-repair-execution-v1":
            raise RepairDenied("invalid repair execution receipt")
        if execution.get("status") != "EXECUTED_PENDING_OUTCOME_VERIFICATION":
            raise RepairDenied(
                "only a successfully applied bounded repair can enter outcome verification"
            )
        proposal = RepairProposal(
            **execution["proposal"]
        )
        self._require_verifiers()
        executor = self._executor(proposal.action_key)
        current = executor.inspect(proposal.params)
        target_present = executor.state_matches(
            current,
            execution["expected_applied_state"],
        )
        measured = self._capture_verifiers(
            case_id=proposal.case_id,
            stage="verification",
            proposal=proposal,
        )
        status = (
            "MEASURED_PENDING_OPERATOR_OUTCOME"
            if target_present
            else "TARGET_STATE_DRIFTED"
        )
        record = {
            "schema": "field-medic-repair-verification-v1",
            "case_id": proposal.case_id,
            "proposal_id": proposal.proposal_id,
            "action_key": proposal.action_key,
            "execution_evidence_id": execution["execution_evidence_id"],
            "target_state_present": target_present,
            "target_state": current,
            "target_state_sha256": self._state_hash(current),
            "engine_measurements": measured,
            "status": status,
            "outcome_claim": "UNCLASSIFIED",
            "operator_outcome_required": True,
            "causal_claim": False,
        }
        verification_evidence = wrap_evidence(
            case_id=proposal.case_id,
            source=Source.AGENT_MEDIC,
            category="repair.verification",
            summary=f"Bounded repair verification: {status}",
            payload=record,
            claim_class=ClaimClass.VERIFICATION,
            provenance={
                "execution_evidence_id": execution["execution_evidence_id"],
                "action_key": proposal.action_key,
            },
        )
        self._ledger(proposal.case_id).append(verification_evidence)
        record["verification_evidence_id"] = verification_evidence.evidence_id
        directory = (
            self._case_dir(proposal.case_id)
            / "repairs"
            / proposal.proposal_id
        )
        save_json(directory / "verification.json", record)
        return record

    def rollback(self, execution: dict[str, Any]) -> dict[str, Any]:
        self.gate.require_rollback_receipt(execution)
        proposal = RepairProposal(**execution["proposal"])
        executor = self._executor(proposal.action_key)
        rollback = self._rollback_exact(
            proposal=proposal,
            before=execution["state_before"],
            expected_applied=execution["expected_applied_state"],
            executor=executor,
        )

        verifier_status = "NOT_REQUESTED"
        verifier_payload = None
        if self.drive is not None and self.net is not None:
            try:
                verifier_payload = self._capture_verifiers(
                    case_id=proposal.case_id,
                    stage="rollback",
                    proposal=proposal,
                )
                verifier_status = "CAPTURED"
            except Exception as exc:
                verifier_status = f"UNAVAILABLE: {exc}"

        record = {
            "schema": "field-medic-repair-rollback-v1",
            "case_id": proposal.case_id,
            "proposal_id": proposal.proposal_id,
            "action_key": proposal.action_key,
            "execution_evidence_id": execution.get("execution_evidence_id"),
            "rollback": rollback,
            "independent_verification_status": verifier_status,
            "independent_verification": verifier_payload,
            "status": rollback["status"],
            "causal_claim": False,
            "generic_shell_used": False,
        }
        rollback_evidence = wrap_evidence(
            case_id=proposal.case_id,
            source=Source.AGENT_MEDIC,
            category="repair.rollback",
            summary=f"Bounded repair rollback: {rollback['status']}",
            payload=record,
            claim_class=ClaimClass.GOVERNANCE,
            provenance={
                "execution_evidence_id": execution.get("execution_evidence_id"),
                "action_key": proposal.action_key,
            },
        )
        self._ledger(proposal.case_id).append(rollback_evidence)
        record["rollback_evidence_id"] = rollback_evidence.evidence_id
        directory = (
            self._case_dir(proposal.case_id)
            / "repairs"
            / proposal.proposal_id
        )
        save_json(directory / "rollback.json", record)
        return record
