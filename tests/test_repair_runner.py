import json
import tempfile
import unittest
from pathlib import Path

from fieldmedic.repair_executors import RepairExecutorError, get_executor
from fieldmedic.repair_governance import (
    RepairDenied,
    create_repair_grant,
    prepare_repair,
    propose_repair,
)
from fieldmedic.repair_runner import RepairRunner


class FakeBackend:
    def __init__(self):
        self.interface = {
            "interface_index": 7,
            "address_family": "IPv4",
            "interface_alias": "Wi-Fi",
            "automatic_metric": True,
            "interface_metric": None,
        }
        self.process = {
            "pid": 4242,
            "process_name": "example",
            "start_time_utc_ticks": 123456789,
            "priority": "Normal",
        }
        self.break_apply = False

    def inspect_interface_metric(self, interface_index, address_family):
        return dict(self.interface)

    def set_interface_metric(
        self, interface_index, address_family, *, automatic_metric, metric
    ):
        if self.break_apply and not automatic_metric:
            return dict(self.interface)
        self.interface = {
            **self.interface,
            "automatic_metric": automatic_metric,
            "interface_metric": None if automatic_metric else metric,
        }
        return dict(self.interface)

    def inspect_process_priority(self, pid):
        return dict(self.process)

    def set_process_priority(self, pid, *, expected_start_ticks, priority):
        if expected_start_ticks != self.process["start_time_utc_ticks"]:
            raise RepairExecutorError("process identity changed")
        self.process = {**self.process, "priority": priority}
        return dict(self.process)


class FakeDrive:
    def __init__(self):
        self.count = 0

    def status(self):
        self.count += 1
        return {"source": "drive", "sample": self.count}


class FakeNet:
    def __init__(self, fail_after=999):
        self.count = 0
        self.fail_after = fail_after

    def snapshot(self):
        self.count += 1
        if self.count > self.fail_after:
            raise RuntimeError("net verifier unavailable")
        return {"source": "net", "sample": self.count}


def case_doc():
    return {
        "schema": "field-medic-case-v1",
        "case_id": "case-1",
        "correlation": {"contradictions": []},
        "evidence": [
            {"evidence_id": "ev-drive", "source": "drivemedic"},
            {"evidence_id": "ev-net", "source": "netmedic"},
        ],
    }


class RepairRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        case_dir = self.home / "cases" / "case-1"
        case_dir.mkdir(parents=True)
        (case_dir / "case.json").write_text(
            json.dumps(case_doc()),
            encoding="utf-8",
        )
        self.backend = FakeBackend()
        self.runner = RepairRunner(
            home=self.home,
            drivemedic="unused",
            netmedic="unused",
            backend=self.backend,
        )
        self.runner.drive = FakeDrive()
        self.runner.net = FakeNet()
        self.proposal = propose_repair(
            case_doc(),
            action_key="windows.interface.metric",
            params={
                "interface_index": 7,
                "address_family": "IPv4",
                "metric": 10,
            },
        )
        self.executor = get_executor(
            self.proposal.action_key,
            self.backend,
        )
        self.preflight = prepare_repair(
            self.proposal,
            executor=self.executor,
        )
        self.grant = create_repair_grant(
            self.proposal,
            self.preflight,
            operator_label="operator",
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_happy_path_never_claims_fixed(self):
        result = self.runner.execute(
            self.proposal,
            self.preflight,
            self.grant,
        )
        self.assertEqual(
            result["status"],
            "EXECUTED_PENDING_OUTCOME_VERIFICATION",
        )
        self.assertEqual(result["outcome_claim"], "UNCLASSIFIED")
        self.assertFalse(result["causal_claim"])
        self.assertEqual(self.backend.interface["interface_metric"], 10)
        self.assertIn("execution_evidence_id", result)

        verification = self.runner.verify(result)
        self.assertEqual(
            verification["status"],
            "MEASURED_PENDING_OPERATOR_OUTCOME",
        )
        self.assertTrue(verification["target_state_present"])
        self.assertTrue(verification["operator_outcome_required"])

    def test_state_change_after_preflight_denies_execution(self):
        self.backend.interface["interface_alias"] = "renamed"
        with self.assertRaises(RepairDenied):
            self.runner.execute(
                self.proposal,
                self.preflight,
                self.grant,
            )

    def test_postcondition_failure_rolls_back(self):
        self.backend.break_apply = True
        result = self.runner.execute(
            self.proposal,
            self.preflight,
            self.grant,
        )
        self.assertEqual(
            result["status"],
            "ROLLED_BACK_POSTCONDITION_FAILED",
        )
        self.assertTrue(self.backend.interface["automatic_metric"])
        self.assertIsNone(self.backend.interface["interface_metric"])

    def test_verifier_failure_after_apply_rolls_back(self):
        self.runner.net = FakeNet(fail_after=1)
        result = self.runner.execute(
            self.proposal,
            self.preflight,
            self.grant,
        )
        self.assertEqual(
            result["status"],
            "ROLLED_BACK_VERIFICATION_CAPTURE_FAILED",
        )
        self.assertTrue(self.backend.interface["automatic_metric"])

    def test_manual_rollback_requires_expected_applied_state(self):
        result = self.runner.execute(
            self.proposal,
            self.preflight,
            self.grant,
        )
        self.backend.interface["interface_metric"] = 99
        with self.assertRaises(RepairDenied):
            self.runner.rollback(result)

    def test_manual_rollback_restores_exact_prestate(self):
        result = self.runner.execute(
            self.proposal,
            self.preflight,
            self.grant,
        )
        rolled = self.runner.rollback(result)
        self.assertEqual(rolled["status"], "ROLLED_BACK")
        self.assertTrue(self.backend.interface["automatic_metric"])
        self.assertIsNone(self.backend.interface["interface_metric"])

    def test_execution_requires_both_independent_verifiers(self):
        self.runner.net = None
        with self.assertRaises(RepairDenied):
            self.runner.execute(
                self.proposal,
                self.preflight,
                self.grant,
            )

    def test_process_pid_reuse_is_denied_by_identity(self):
        process_proposal = propose_repair(
            case_doc(),
            action_key="windows.process.priority",
            params={"pid": 4242, "priority": "BelowNormal"},
        )
        process_executor = get_executor(
            process_proposal.action_key,
            self.backend,
        )
        preflight = prepare_repair(
            process_proposal,
            executor=process_executor,
        )
        grant = create_repair_grant(
            process_proposal,
            preflight,
            operator_label="operator",
        )
        self.backend.process["start_time_utc_ticks"] += 1
        with self.assertRaises(RepairDenied):
            self.runner.execute(process_proposal, preflight, grant)


if __name__ == "__main__":
    unittest.main()
