from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from typing import Any

from .specialists import SPECIALISTS


_ALLOWED_TIERS = {"deterministic", "utility", "specialist", "frontier"}


class BrainCRoutingError(RuntimeError):
    pass


def validate_brainc_response(payload: dict[str, Any], *, frontier_allowed: bool = False) -> dict[str, Any]:
    if payload.get("schema") != "field-medic-brainc-routing-response-v1":
        raise BrainCRoutingError("unexpected BrainC routing schema")
    specialist_ids = payload.get("specialist_ids")
    if not isinstance(specialist_ids, list) or not specialist_ids:
        raise BrainCRoutingError("BrainC must return at least one specialist_id")
    unknown = [item for item in specialist_ids if item not in SPECIALISTS]
    if unknown:
        raise BrainCRoutingError(f"BrainC returned unknown specialist IDs: {unknown}")

    tier = payload.get("reasoning_tier")
    if tier not in _ALLOWED_TIERS:
        raise BrainCRoutingError(f"invalid reasoning_tier: {tier}")
    if tier == "frontier" and not frontier_allowed:
        raise BrainCRoutingError("BrainC requested frontier reasoning while the frontier gate is closed")

    reasons = payload.get("reasons", [])
    if not isinstance(reasons, list) or not all(isinstance(item, str) for item in reasons):
        raise BrainCRoutingError("BrainC reasons must be a list of strings")

    return {
        "schema": payload["schema"],
        "specialist_ids": list(dict.fromkeys(specialist_ids)),
        "reasoning_tier": tier,
        "escalate": bool(payload.get("escalate", False)),
        "reasons": reasons,
        "authority_ceiling": "infer",
    }


class BrainCRouter:
    """Optional subprocess bridge for SuperPhiVessel/BrainC routing."""

    def __init__(self, binary: str | None = None):
        self.binary = binary or os.environ.get("BRAINC_ROUTER_BIN")

    @property
    def available(self) -> bool:
        return bool(self.binary and Path(self.binary).exists())

    def route(self, request: dict[str, Any], *, frontier_allowed: bool = False) -> dict[str, Any]:
        if not self.available:
            raise BrainCRoutingError("BrainC router binary is not configured")
        cp = subprocess.run(
            [str(self.binary)],
            input=json.dumps(request),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if cp.returncode != 0:
            raise BrainCRoutingError(
                f"BrainC router failed ({cp.returncode}): {cp.stderr.strip()}"
            )
        try:
            payload = json.loads(cp.stdout)
        except json.JSONDecodeError as exc:
            raise BrainCRoutingError(f"BrainC returned invalid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise BrainCRoutingError("BrainC response root must be an object")
        return validate_brainc_response(payload, frontier_allowed=frontier_allowed)
