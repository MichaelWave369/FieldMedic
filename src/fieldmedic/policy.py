from __future__ import annotations
from .models import Authority


class AuthorityDenied(PermissionError):
    pass


class RealityGate:
    """Fail-closed authority boundary for Agent Medic v0.1."""

    ALLOWED = {Authority.OBSERVE, Authority.INFER, Authority.PROPOSE}

    def require(self, authority: Authority) -> None:
        if authority not in self.ALLOWED:
            raise AuthorityDenied(
                "Agent Medic v0.1 cannot execute repair/change actions. "
                "Operator authorization plus a bounded executor must be added explicitly."
            )
