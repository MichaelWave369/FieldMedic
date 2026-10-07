import unittest

from fieldmedic.synthesis import build_synthesis, validate_synthesis, SynthesisValidationError


class SynthesisTests(unittest.TestCase):
    def test_claims_cite_source_evidence(self):
        receipt = build_synthesis(
            case_id="case-1",
            symptom="wifi reset",
            domain="mixed",
            correlation={
                "evidence_ids": ["ev-a", "ev-b"],
                "contradictions": [],
                "diagnostic_tensions": [{
                    "left_event_id": "ev-a:event:0",
                    "right_event_id": "ev-b:event:0",
                }],
                "cross_source_pairs": [],
                "limits": ["timing is not causation"],
            },
            correlation_evidence_id="ev-corr",
            specialist_plan={"specialist_ids": ["case.correlation", "case.synthesis"]},
            reasoning_plan={"requested_tier": "specialist"},
        )
        self.assertEqual(receipt["claims"][0]["evidence_ids"], ["ev-a", "ev-b"])
        self.assertFalse(receipt["causal_claim"])

    def test_unknown_evidence_reference_is_rejected(self):
        bad = {
            "schema": "field-medic-synthesis-v1",
            "claims": [{"evidence_ids": ["invented"], "causal_claim": False}],
            "causal_claim": False,
        }
        with self.assertRaises(SynthesisValidationError):
            validate_synthesis(bad, available_evidence_ids={"ev-real"})


if __name__ == "__main__":
    unittest.main()
