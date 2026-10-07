import unittest
from pathlib import Path
from unittest.mock import patch

from fieldmedic.promotion import build_promotion_candidate


DISCOVERY = {
    "drivemedic": {
        "present": True,
        "version": "DriveMedic 1.0.0-rc13",
    },
    "netmedic": {
        "present": True,
        "version": "Parallax NetMedic v0.34.0",
    },
}


def gate(status):
    return {
        "status": status,
        "errors": [],
        "receipt_sha256": "a" * 64,
    }


class PromotionTests(unittest.TestCase):
    @patch("fieldmedic.promotion.discover_engines", return_value=DISCOVERY)
    @patch(
        "fieldmedic.promotion.install_smoke_gate_from_home",
        return_value=gate("QUALIFIED_BY_LOCAL_RECEIPT"),
    )
    @patch(
        "fieldmedic.promotion.qualification_gate_from_home",
        return_value=gate("QUALIFIED_BY_LOCAL_RECEIPT"),
    )
    @patch(
        "fieldmedic.promotion.external_gate_from_home",
        return_value=gate("QUALIFIED_BY_IMPORTED_EVIDENCE"),
    )
    def test_all_five_gates_are_required_for_stable_packaging(
        self,
        external,
        repair,
        smoke,
        discovery,
    ):
        result = build_promotion_candidate(Path("."))
        self.assertEqual(result["status"], "READY_FOR_STABLE_PACKAGING")
        self.assertEqual(result["blocking_gates"], [])
        self.assertEqual(external.call_count, 3)

    @patch("fieldmedic.promotion.discover_engines", return_value=DISCOVERY)
    @patch(
        "fieldmedic.promotion.install_smoke_gate_from_home",
        return_value=gate("UNPROVEN_BY_LOCAL_RECEIPT"),
    )
    @patch(
        "fieldmedic.promotion.qualification_gate_from_home",
        return_value=gate("QUALIFIED_BY_LOCAL_RECEIPT"),
    )
    @patch(
        "fieldmedic.promotion.external_gate_from_home",
        return_value=gate("QUALIFIED_BY_IMPORTED_EVIDENCE"),
    )
    def test_one_missing_gate_blocks_stable_packaging(
        self,
        external,
        repair,
        smoke,
        discovery,
    ):
        result = build_promotion_candidate(Path("."))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(
            result["blocking_gates"][0]["gate"],
            "windows_install_smoke",
        )


if __name__ == "__main__":
    unittest.main()
