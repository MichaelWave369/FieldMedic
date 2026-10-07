import unittest

from fieldmedic.specialists import SPECIALISTS, plan_specialists


class SpecialistTests(unittest.TestCase):
    def test_wifi_storage_mixed_case_routes_to_precise_specialists(self):
        plan = plan_specialists(
            "wifi drops while nvme stalls",
            "mixed",
            {"cross_source_pairs": [{"x": 1}], "contradictions": [], "diagnostic_tensions": [], "evidence_ids": ["a", "b"]},
        )
        self.assertIn("network.wifi", plan["specialist_ids"])
        self.assertIn("host.storage", plan["specialist_ids"])
        self.assertIn("case.correlation", plan["specialist_ids"])
        self.assertEqual(plan["authority_ceiling"], "infer")

    def test_all_specialists_are_nonexecuting(self):
        self.assertTrue(all(item.max_authority == "infer" for item in SPECIALISTS.values()))


if __name__ == "__main__":
    unittest.main()
