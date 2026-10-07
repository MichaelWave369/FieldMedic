import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from fieldmedic.experiments import (
    ExperimentApprovalError,
    ExperimentGate,
    create_approval,
    propose_experiment,
    suggest_experiment_template,
)


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        self.proposal = propose_experiment(
            case_id="case-1",
            netmedic_case="C:/cases/network-1",
            name="Wi-Fi vs Ethernet",
            design_key="connection",
            arm_a="wifi",
            arm_b="ethernet",
            test_label="ethernet-ab",
            controls={"vpn": "off", "location": "desk"},
            evidence_ids=["ev-a", "ev-b"],
        )

    def test_suggest_wifi_template_does_not_claim_causation(self):
        proposal = suggest_experiment_template(
            symptom="wifi disconnects",
            case_id="case-1",
            netmedic_case="C:/cases/network-1",
            evidence_ids=["ev-a"],
        )
        self.assertIsNotNone(proposal)
        self.assertFalse(proposal.causal_claim)
        self.assertEqual(proposal.arm_a, "wifi")
        self.assertEqual(proposal.arm_b, "ethernet")

    def test_dns_template_refuses_to_invent_resolvers(self):
        self.assertIsNone(suggest_experiment_template(
            symptom="dns resolver is flaky",
            case_id="case-1",
            netmedic_case="C:/cases/network-1",
            evidence_ids=[],
        ))

    def test_approval_is_bound_to_proposal_hash(self):
        approval = create_approval(
            self.proposal,
            operator_label="operator",
            scopes=["netmedic.protocol.freeze"],
        )
        tampered = replace(self.proposal, arm_b="cellular")
        with self.assertRaises(ExperimentApprovalError):
            ExperimentGate().require(
                proposal=tampered,
                approval=approval,
                scope="netmedic.protocol.freeze",
            )

    def test_capture_requires_physical_confirmations(self):
        approval = create_approval(
            self.proposal,
            operator_label="operator",
            scopes=["netmedic.protocol.preflight", "netmedic.protocol.capture"],
            confirmations={"arm": True, "machine_stable": True, "test_context": True, "controls": ["vpn"]},
        )
        with self.assertRaises(ExperimentApprovalError):
            ExperimentGate().require(
                proposal=self.proposal,
                approval=approval,
                scope="netmedic.protocol.capture",
                require_physical_confirmations=True,
            )

    def test_capture_all_confirmations_pass(self):
        approval = create_approval(
            self.proposal,
            operator_label="operator",
            scopes=["netmedic.protocol.preflight", "netmedic.protocol.capture"],
            confirmations={
                "arm": True,
                "machine_stable": True,
                "test_context": True,
                "controls": ["vpn", "location"],
            },
        )
        ExperimentGate().require(
            proposal=self.proposal,
            approval=approval,
            scope="netmedic.protocol.capture",
            require_physical_confirmations=True,
        )

    def test_stale_physical_confirmations_are_rejected(self):
        approval = create_approval(
            self.proposal,
            operator_label="operator",
            scopes=["netmedic.protocol.preflight", "netmedic.protocol.capture"],
            ttl_minutes=30,
            confirmations={
                "arm": True,
                "machine_stable": True,
                "test_context": True,
                "controls": ["vpn", "location"],
            },
        )
        later = datetime.now(timezone.utc) + timedelta(minutes=11)
        with self.assertRaises(ExperimentApprovalError):
            ExperimentGate().require(
                proposal=self.proposal,
                approval=approval,
                scope="netmedic.protocol.capture",
                now=later,
                require_physical_confirmations=True,
            )

    def test_expired_approval_is_rejected(self):
        approval = create_approval(
            self.proposal,
            operator_label="operator",
            scopes=["netmedic.protocol.freeze"],
            ttl_minutes=1,
        )
        later = datetime.now(timezone.utc) + timedelta(minutes=2)
        with self.assertRaises(ExperimentApprovalError):
            ExperimentGate().require(
                proposal=self.proposal,
                approval=approval,
                scope="netmedic.protocol.freeze",
                now=later,
            )


if __name__ == "__main__":
    unittest.main()
