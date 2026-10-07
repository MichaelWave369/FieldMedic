import unittest
from fieldmedic.envelope import wrap_evidence
from fieldmedic.models import Source

class ContractTests(unittest.TestCase):
    def test_observation_is_noncausal_and_hashed(self):
        e = wrap_evidence(case_id="case-1", source=Source.DRIVEMEDIC,
                          category="host.status", summary="x", payload={"a": 1})
        self.assertFalse(e.causal_claim)
        self.assertEqual(e.claim_class, "observation")
        self.assertEqual(len(e.payload_sha256), 64)
        self.assertEqual(e.authority, "observe")

if __name__ == '__main__': unittest.main()
