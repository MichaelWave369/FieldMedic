import unittest
from fieldmedic.policy import RealityGate, AuthorityDenied
from fieldmedic.models import Authority

class GovernanceTests(unittest.TestCase):
    def test_execute_denied(self):
        with self.assertRaises(AuthorityDenied):
            RealityGate().require(Authority.EXECUTE)
    def test_propose_allowed(self):
        RealityGate().require(Authority.PROPOSE)

if __name__ == '__main__': unittest.main()
