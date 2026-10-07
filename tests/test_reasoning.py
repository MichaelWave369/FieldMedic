import unittest

from fieldmedic.local_models import LocalModel, choose_model
from fieldmedic.reasoning import plan_reasoning


class ReasoningTests(unittest.TestCase):
    def setUp(self):
        self.models = [
            LocalModel("ollama", "tiny:4b", size_bytes=4_000_000_000, parameter_billions=4),
            LocalModel("ollama", "medium:14b", size_bytes=10_000_000_000, parameter_billions=14),
            LocalModel("ollama", "large:32b", size_bytes=20_000_000_000, parameter_billions=32),
        ]

    def test_utility_uses_cheapest_model(self):
        self.assertEqual(choose_model(self.models, "utility").name, "tiny:4b")

    def test_specialist_avoids_largest_by_default(self):
        self.assertEqual(choose_model(self.models, "specialist").name, "medium:14b")

    def test_frontier_is_not_invoked_by_plan(self):
        plan = plan_reasoning(
            domain="mixed",
            correlation={"contradictions": [], "diagnostic_tensions": [1], "source_count": 2},
            specialist_plan={"specialist_ids": ["case.correlation"]},
            local_models=self.models,
        )
        self.assertEqual(plan["requested_tier"], "specialist")
        self.assertFalse(plan["frontier"]["invoked"])
        self.assertFalse(plan["frontier"]["eligible_now"])
        self.assertEqual(plan["selected_local_model"]["name"], "medium:14b")

    def test_no_evidence_does_not_spend_model_compute(self):
        plan = plan_reasoning(
            domain="unknown",
            correlation={"contradictions": [], "diagnostic_tensions": [], "source_count": 0},
            specialist_plan={"specialist_ids": ["case.evidence"]},
            local_models=self.models,
        )
        self.assertEqual(plan["requested_tier"], "deterministic")
        self.assertIsNone(plan["selected_local_model"])


if __name__ == "__main__":
    unittest.main()
