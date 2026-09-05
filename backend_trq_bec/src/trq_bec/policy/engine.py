"""Policy is the only component that converts verified inputs into a decision."""

from __future__ import annotations

from dataclasses import dataclass

from ..canonical import sha3_hex
from ..contracts import Decision, RiskResult
from ..errors import PolicyError


@dataclass(frozen=True, slots=True)
class Policy:
    version: str
    q_min_bps: int
    low_risk_bps: int
    high_risk_bps: int
    profile: str = "LAB"

    def __post_init__(self) -> None:
        if not self.version:
            raise PolicyError("policy version is required")
        if not 0 <= self.low_risk_bps < self.high_risk_bps <= 10_000:
            raise PolicyError("risk thresholds are invalid")
        if not 0 <= self.q_min_bps <= 10_000:
            raise PolicyError("coverage threshold is invalid")
        if self.profile not in {"LAB", "PRODUCTION"}:
            raise PolicyError("unknown policy profile")

    def to_dict(self) -> dict[str, str | int]:
        return {
            "version": self.version,
            "q_min_bps": self.q_min_bps,
            "low_risk_bps": self.low_risk_bps,
            "high_risk_bps": self.high_risk_bps,
            "profile": self.profile,
        }

    @property
    def digest(self) -> str:
        return sha3_hex(self.to_dict(), "TRQ-BEC/policy/v1")


class PolicyEngine:
    def __init__(self, policy: Policy) -> None:
        self.policy = policy

    def decide(self, crypto_ok: bool, risk: RiskResult | None, step_up_passed: bool = False) -> Decision:
        if not crypto_ok:
            return Decision.DENY
        if risk is None or risk.coverage_bps < self.policy.q_min_bps:
            return Decision.STEP_UP
        if risk.risk_bps < self.policy.low_risk_bps:
            return Decision.ALLOW
        if risk.risk_bps < self.policy.high_risk_bps:
            return Decision.ALLOW if step_up_passed else Decision.STEP_UP
        return Decision.HOLD_OR_REVIEW

