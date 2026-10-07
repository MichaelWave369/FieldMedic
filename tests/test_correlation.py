import unittest

from fieldmedic.correlation import correlate_evidence, normalize_timestamp
from fieldmedic.envelope import wrap_evidence
from fieldmedic.models import Source


class CorrelationTests(unittest.TestCase):
    def _evidence(self, source, payload, evidence_summary="test"):
        return wrap_evidence(
            case_id="case-test",
            source=source,
            category="test",
            summary=evidence_summary,
            payload=payload,
            observed_at="2026-10-07T18:00:00Z",
        )

    def test_iso_timestamp_is_normalized_to_utc(self):
        self.assertEqual(
            normalize_timestamp("2026-10-07T11:00:00-07:00"),
            "2026-10-07T18:00:00.000Z",
        )

    def test_unix_milliseconds_are_supported(self):
        self.assertEqual(
            normalize_timestamp(1791396000000),
            "2026-10-07T18:00:00.000Z",
        )

    def test_cross_source_events_inside_window_are_linked(self):
        host = self._evidence(Source.DRIVEMEDIC, {
            "events": [{"timestamp": "2026-10-07T18:00:00Z", "component": "wifi", "status": "reset"}]
        })
        net = self._evidence(Source.NETMEDIC, {
            "events": [{"timestamp": "2026-10-07T18:00:03Z", "component": "wan", "status": "healthy"}]
        })
        receipt = correlate_evidence([host, net], window_seconds=5)
        self.assertEqual(len(receipt["cross_source_pairs"]), 1)
        self.assertEqual(receipt["cross_source_pairs"][0]["delta_seconds"], 3.0)
        self.assertGreater(receipt["temporal_association_strength"], 0)

    def test_temporal_association_never_becomes_causal_claim(self):
        host = self._evidence(Source.DRIVEMEDIC, {"timestamp": "2026-10-07T18:00:00Z"})
        net = self._evidence(Source.NETMEDIC, {"timestamp": "2026-10-07T18:00:00Z"})
        receipt = correlate_evidence([host, net])
        self.assertFalse(receipt["causal_claim"])
        self.assertIn("not probability", receipt["association_strength_semantics"])

    def test_same_subject_opposite_states_are_contradiction(self):
        host = self._evidence(Source.DRIVEMEDIC, {
            "timestamp": "2026-10-07T18:00:00Z", "component": "wifi", "status": "disconnected"
        })
        net = self._evidence(Source.NETMEDIC, {
            "timestamp": "2026-10-07T18:00:02Z", "component": "wifi", "status": "healthy"
        })
        receipt = correlate_evidence([host, net], window_seconds=5)
        self.assertEqual(len(receipt["contradictions"]), 1)

    def test_different_subject_opposite_states_are_tension_not_contradiction(self):
        host = self._evidence(Source.DRIVEMEDIC, {
            "timestamp": "2026-10-07T18:00:00Z", "component": "wifi-adapter", "status": "reset"
        })
        net = self._evidence(Source.NETMEDIC, {
            "timestamp": "2026-10-07T18:00:02Z", "component": "wan", "status": "healthy"
        })
        receipt = correlate_evidence([host, net], window_seconds=5)
        self.assertEqual(receipt["contradictions"], [])
        self.assertEqual(len(receipt["diagnostic_tensions"]), 1)


if __name__ == "__main__":
    unittest.main()
