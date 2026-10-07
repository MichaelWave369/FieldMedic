import unittest
from fieldmedic.router import route

class RouterTests(unittest.TestCase):
    def test_network(self):
        self.assertEqual(route("wifi keeps disconnecting from the internet").domain, "network")
    def test_host(self):
        self.assertEqual(route("nvme disk latency makes windows slow").domain, "host")
    def test_mixed(self):
        self.assertEqual(route("windows freezes when wifi disconnects").domain, "mixed")
    def test_unknown_escalates(self):
        d = route("it acts weird sometimes")
        self.assertEqual(d.domain, "unknown")
        self.assertTrue(d.escalate)

if __name__ == '__main__': unittest.main()
