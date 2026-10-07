import unittest

from fieldmedic.brainc import validate_brainc_response, BrainCRoutingError


class BrainCTests(unittest.TestCase):
    def test_valid_route_is_bounded_to_inference(self):
        result = validate_brainc_response({
            "schema": "field-medic-brainc-routing-response-v1",
            "specialist_ids": ["network.wifi", "case.synthesis"],
            "reasoning_tier": "specialist",
            "escalate": True,
            "reasons": ["mixed evidence"],
        })
        self.assertEqual(result["authority_ceiling"], "infer")

    def test_unknown_specialist_is_rejected(self):
        with self.assertRaises(BrainCRoutingError):
            validate_brainc_response({
                "schema": "field-medic-brainc-routing-response-v1",
                "specialist_ids": ["root.shell"],
                "reasoning_tier": "utility",
                "escalate": False,
                "reasons": [],
            })

    def test_frontier_request_is_rejected_while_gate_closed(self):
        with self.assertRaises(BrainCRoutingError):
            validate_brainc_response({
                "schema": "field-medic-brainc-routing-response-v1",
                "specialist_ids": ["case.synthesis"],
                "reasoning_tier": "frontier",
                "escalate": True,
                "reasons": ["because expensive sounds fun"],
            }, frontier_allowed=False)


if __name__ == "__main__":
    unittest.main()
