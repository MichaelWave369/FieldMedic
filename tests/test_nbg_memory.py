import tempfile
import unittest
from pathlib import Path

from fieldmedic.nbg_memory import (
    DiagnosticMemoryStore,
    case_to_inferred_memory,
    derive_verified_outcome,
    fnv1a32,
    memory_reliability,
    merge_specialist_hints,
    stable_json,
    verified_outcome_weight,
)


def sample_case(case_id="case-1", symptom="wifi disconnects while Windows freezes"):
    return {
        "case_id": case_id,
        "symptom": symptom,
        "routing": {"domain": "mixed"},
        "specialist_plan": {
            "specialist_ids": ["network.wifi", "host.windows", "case.correlation"]
        },
        "correlation": {"temporal_association_strength": 0.7},
        "synthesis": {
            "claims": [{
                "kind": "diagnostic-tension",
                "text": "Wi-Fi and host state changed in the same bounded window.",
                "evidence_ids": ["ev-a", "ev-b"],
                "causal_claim": False,
            }]
        },
        "experiment_proposal": None,
        "evidence": [
            {
                "evidence_id": "ev-a",
                "source": "drivemedic",
                "claim_class": "observation",
                "category": "host.timeline",
                "payload_sha256": "a" * 64,
                "observed_at": "2026-10-07T18:00:00Z",
                "ingested_at": "2026-10-07T18:00:01Z",
            },
            {
                "evidence_id": "ev-b",
                "source": "netmedic",
                "claim_class": "observation",
                "category": "network.snapshot",
                "payload_sha256": "b" * 64,
                "observed_at": "2026-10-07T18:00:02Z",
                "ingested_at": "2026-10-07T18:00:03Z",
            },
        ],
    }


class NBGMemoryTests(unittest.TestCase):
    def test_fingerprint_matches_standard_ascii_fnv1a_vector(self):
        self.assertEqual(fnv1a32("hello"), "fnv1a32:4f9f2cab")

    def test_stable_json_matches_javascript_integer_float_semantics(self):
        self.assertEqual(stable_json({"x": 1.0, "zero": -0.0}), '{"x":1,"zero":0}')

    def test_memory_hints_only_add_known_specialists_and_never_remove_current(self):
        merged, added = merge_specialist_hints(
            ["host.windows"],
            {
                "specialistHints": [
                    {"specialistId": "network.wifi", "score": 0.8},
                    {"specialistId": "root.shell", "score": 999},
                    {"specialistId": "host.storage", "score": 0.01},
                ]
            },
            known_ids={"host.windows", "network.wifi", "host.storage"},
        )
        self.assertEqual(merged[0], "host.windows")
        self.assertIn("network.wifi", merged)
        self.assertNotIn("root.shell", merged)
        self.assertNotIn("host.storage", merged)
        self.assertEqual(added, ["network.wifi"])

    def test_case_candidate_is_nbg_epistemic_inferred_and_non_authorizing(self):
        memory = case_to_inferred_memory(sample_case())
        self.assertEqual(memory["schemaVersion"], "NBG_EPISTEMIC_1")
        self.assertEqual(memory["epistemic"]["origin"], "INFERRED")
        self.assertFalse(memory["epistemic"]["authority"]["actionAuthorized"])
        self.assertFalse(memory["content"]["causalClaim"])

    def test_verified_outcome_derives_new_memory_instead_of_mutating_source(self):
        source = case_to_inferred_memory(sample_case())
        derived, receipt = derive_verified_outcome(
            source,
            outcome="VERIFIED_FAILURE",
            verification_evidence_id="verify-1",
            details="driver rollback did not reproduce improvement",
        )
        self.assertEqual(source["epistemic"]["origin"], "INFERRED")
        self.assertEqual(source["content"]["outcome"]["status"], "UNRESOLVED")
        self.assertEqual(derived["epistemic"]["origin"], "VERIFIED")
        self.assertEqual(derived["content"]["outcome"]["status"], "VERIFIED_FAILURE")
        self.assertEqual(
            derived["epistemic"]["lineage"]["parentMemoryId"],
            source["memoryId"],
        )
        self.assertFalse(receipt["authorityChanged"])

    def test_verified_failure_and_success_have_equal_memory_weight(self):
        self.assertEqual(
            verified_outcome_weight("VERIFIED_FAILURE"),
            verified_outcome_weight("VERIFIED_SUCCESS"),
        )

    def test_negative_verified_case_is_retained_and_queryable(self):
        with tempfile.TemporaryDirectory() as td:
            store = DiagnosticMemoryStore(Path(td))
            source = case_to_inferred_memory(sample_case())
            store.admit(
                source,
                operator_label="operator",
                reason="retain diagnostic case",
                case_id="case-1",
            )
            derived, receipt = derive_verified_outcome(
                source,
                outcome="VERIFIED_NO_EFFECT",
                verification_evidence_id="verify-no-effect",
            )
            store.admit(
                derived,
                operator_label="operator",
                reason="retain verified no-effect outcome",
                case_id="case-1",
            )
            store.append_transition(receipt)
            matches = store.query(
                symptom="wifi disconnects and Windows freezes",
                domain="mixed",
                specialist_ids=["network.wifi", "host.windows"],
            )
            self.assertTrue(any(
                item.memory["content"]["outcome"]["status"] == "VERIFIED_NO_EFFECT"
                for item in matches
            ))
            self.assertEqual(memory_reliability(derived), 1.0)

    def test_routing_hints_are_model_independent_and_provenance_preserving(self):
        with tempfile.TemporaryDirectory() as td:
            store = DiagnosticMemoryStore(Path(td))
            memory = case_to_inferred_memory(sample_case())
            store.admit(
                memory,
                operator_label="operator",
                reason="test",
                case_id="case-1",
            )
            hints = store.routing_hints(
                symptom="wifi disconnects while Windows freezes",
                domain="mixed",
                specialist_ids=["network.wifi"],
            )
            self.assertEqual(
                hints["policy"],
                "deterministic-provenance-preserving-case-similarity",
            )
            self.assertFalse(hints["causalClaim"])
            self.assertTrue(hints["matches"])
            match = hints["matches"][0]
            self.assertIn("recordFingerprint", match)
            self.assertIn("evidence", match)
            self.assertIn("lineage", match)


if __name__ == "__main__":
    unittest.main()
