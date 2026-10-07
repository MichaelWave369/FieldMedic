import tempfile
import unittest
from pathlib import Path

from fieldmedic.experiment_runner import GovernedExperimentRunner
from fieldmedic.experiments import create_approval, propose_experiment


class FakeDrive:
    def __init__(self):
        self.calls = 0

    def status(self):
        self.calls += 1
        return {"timestamp": f"2026-10-07T19:00:0{self.calls}Z", "host": "ok", "sample": self.calls}


class FakeNet:
    def freeze_protocol(self, proposal):
        return {"schema": "0.34-protocol-freeze", "fingerprint": "fp-test"}

    def preflight_protocol(self, **kwargs):
        path = Path(kwargs["output_path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"schema":"0.34-preflight","status":"READY"}', encoding="utf-8")
        return {
            "schema": "0.34-preflight",
            "status": "READY",
            "_local_receipt_path": str(path),
        }

    def execute_protocol(self, **kwargs):
        self.preflight_path = kwargs["preflight_receipt"]
        return {"schema": "0.34-experiment-execution", "status": "captured"}

    def matched_protocol(self, **kwargs):
        return {"schema": "0.34-matched-experiment", "pairs": 1}


class ExperimentRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.proposal = propose_experiment(
            case_id="case-1",
            netmedic_case="C:/cases/network-1",
            name="Wi-Fi vs Ethernet",
            design_key="connection",
            arm_a="wifi",
            arm_b="ethernet",
            test_label="ethernet-ab",
            controls={"vpn": "off"},
            evidence_ids=["ev-a"],
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_capture_brackets_netmedic_with_host_state_and_ledgers_receipt(self):
        approval = create_approval(
            self.proposal,
            operator_label="operator",
            scopes=["netmedic.protocol.preflight", "netmedic.protocol.capture"],
            confirmations={
                "arm": True,
                "machine_stable": True,
                "test_context": True,
                "controls": ["vpn"],
            },
        )
        runner = GovernedExperimentRunner(
            home=self.home,
            drivemedic="unused-drive",
            netmedic="unused-net",
        )
        runner.drive = FakeDrive()
        runner.net = FakeNet()

        record = runner.capture(
            self.proposal,
            approval,
            protocol_fingerprint="fp-test",
        )

        self.assertEqual(record["host_before"]["sample"], 1)
        self.assertEqual(record["host_after"]["sample"], 2)
        self.assertFalse(record["causal_claim"])
        self.assertFalse(record["repair_authority"])
        self.assertTrue(record["evidence_id"].startswith("ev-"))
        self.assertTrue(Path(runner.net.preflight_path).exists())
        ledger = self.home / "cases" / "case-1" / "evidence.jsonl"
        self.assertTrue(ledger.exists())
        self.assertIn("experiment.capture", ledger.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
