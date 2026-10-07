import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from fieldmedic.repair_executors import (
    RepairExecutorError,
    normalize_params,
)
from fieldmedic.repair_governance import (
    RepairDenied,
    RepairGate,
    create_repair_grant,
    prepare_repair,
    propose_repair,
)


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

    def inspect_interface_metric(self, interface_index, address_family):
        return dict(self.interface)

    def set_interface_metric(
        self, interface_index, address_family, *, automatic_metric, metric
    ):
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


def case(*, contradictions=False, include_net=True, include_drive=True):
    evidence = []
    if include_drive:
        evidence.append({"evidence_id": "ev-drive", "source": "drivemedic"})
    if include_net:
        evidence.append({"evidence_id": "ev-net", "source": "netmedic"})
    return {
        "case_id": "case-1",
        "correlation": {
            "contradictions": [{"x": 1}] if contradictions else [],
        },
        "evidence": evidence,
    }


class RepairGovernanceTests(unittest.TestCase):
    def test_unknown_or_extra_params_are_rejected(self):
        with self.assertRaises(RepairExecutorError):
            normalize_params(
                "windows.process.priority",
                {"pid": 1, "priority": "Normal", "command": "whoami"},
            )

    def test_process_priority_cannot_be_raised_above_normal(self):
        with self.assertRaises(RepairExecutorError):
            normalize_params(
                "windows.process.priority",
                {"pid": 1, "priority": "High"},
            )

    def test_interface_repair_requires_netmedic_source_evidence(self):
        with self.assertRaises(RepairDenied):
            propose_repair(
                case(include_net=False),
                action_key="windows.interface.metric",
                params={
                    "interface_index": 7,
                    "address_family": "IPv4",
                    "metric": 10,
                },
            )

    def test_process_repair_requires_drivemedic_source_evidence(self):
        with self.assertRaises(RepairDenied):
            propose_repair(
                case(include_drive=False),
                action_key="windows.process.priority",
                params={"pid": 4242, "priority": "BelowNormal"},
            )

    def test_unresolved_contradiction_denies_repair(self):
        with self.assertRaises(RepairDenied):
            propose_repair(
                case(contradictions=True),
                action_key="windows.interface.metric",
                params={
                    "interface_index": 7,
                    "address_family": "IPv4",
                    "metric": 10,
                },
            )

    def test_grant_is_bound_to_exact_preflight(self):
        backend = FakeBackend()
        proposal = propose_repair(
            case(),
            action_key="windows.interface.metric",
            params={
                "interface_index": 7,
                "address_family": "IPv4",
                "metric": 10,
            },
        )
        from fieldmedic.repair_executors import get_executor
        preflight = prepare_repair(
            proposal,
            executor=get_executor(proposal.action_key, backend),
        )
        grant = create_repair_grant(
            proposal,
            preflight,
            operator_label="operator",
        )
        tampered = dict(preflight)
        tampered["state_before_sha256"] = "0" * 64
        with self.assertRaises(RepairDenied):
            RepairGate().require_execute(
                proposal=proposal,
                preflight=tampered,
                grant=grant,
                case=case(),
            )

    def test_expired_grant_denies_execution(self):
        backend = FakeBackend()
        proposal = propose_repair(
            case(),
            action_key="windows.interface.metric",
            params={
                "interface_index": 7,
                "address_family": "IPv4",
                "metric": 10,
            },
        )
        from fieldmedic.repair_executors import get_executor
        preflight = prepare_repair(
            proposal,
            executor=get_executor(proposal.action_key, backend),
        )
        grant = create_repair_grant(
            proposal,
            preflight,
            operator_label="operator",
            ttl_minutes=1,
        )
        later = datetime.now(timezone.utc) + timedelta(minutes=2)
        with self.assertRaises(RepairDenied):
            RepairGate().require_execute(
                proposal=proposal,
                preflight=preflight,
                grant=grant,
                case=case(),
                now=later,
            )


if __name__ == "__main__":
    unittest.main()
