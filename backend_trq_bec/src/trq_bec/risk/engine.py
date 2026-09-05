"""Deterministic, explainable laboratory risk index.

The result is an HEURISTIC_INDEX, never represented as a calibrated probability.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from ..contracts import Observation, RiskResult, ScoreKind


@dataclass(frozen=True, slots=True)
class SignalRule:
    name: str
    expected_weight: int
    risk_when_true_bps: int
    reason_code: str


DEFAULT_RULES = (
    SignalRule("device_key_known", 30, -1_000, "KNOWN_DEVICE_KEY"),
    SignalRule("session_context_changed", 20, 2_000, "SESSION_CONTEXT_CHANGED"),
    SignalRule("rate_increase", 20, 2_500, "RATE_INCREASE"),
    SignalRule("geo_velocity_high", 20, 3_000, "GEO_VELOCITY_HIGH"),
    SignalRule("collector_health_ok", 10, -500, "COLLECTOR_HEALTH_OK"),
)


class ContextRiskEngine:
    def __init__(
        self,
        allowed_sources: set[str],
        *,
        rules: tuple[SignalRule, ...] = DEFAULT_RULES,
        detector_version: str = "risk-0.1.0",
        clock=time.time,
    ) -> None:
        self.allowed_sources = frozenset(allowed_sources)
        self.rules = rules
        self.detector_version = detector_version
        self.clock = clock

    @staticmethod
    def _as_bool(value: str) -> bool | None:
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
        return None

    def evaluate(self, observations: list[Observation]) -> RiskResult:
        now = int(self.clock())
        by_name: dict[str, Observation] = {}
        for observation in observations:
            valid = (
                observation.source in self.allowed_sources
                and observation.observed_at <= now <= observation.expires_at
                and observation.quality_bps >= 5_000
                and observation.integrity_bps >= 8_000
                and self._as_bool(observation.value) is not None
            )
            if valid:
                current = by_name.get(observation.name)
                if current is None or observation.observed_at > current.observed_at:
                    by_name[observation.name] = observation

        expected_weight = sum(rule.expected_weight for rule in self.rules)
        valid_weight = 0
        weighted_quality = 0
        risk = 1_500
        reasons: list[str] = []
        evidence_refs: list[str] = []

        for rule in self.rules:
            observation = by_name.get(rule.name)
            if observation is None:
                continue
            valid_weight += rule.expected_weight
            weighted_quality += rule.expected_weight * min(observation.quality_bps, observation.integrity_bps)
            evidence_refs.append(observation.evidence_ref)
            value = self._as_bool(observation.value)
            if value:
                risk += rule.risk_when_true_bps
                reasons.append(rule.reason_code)
            elif rule.name == "device_key_known":
                risk += 2_500
                reasons.append("NEW_OR_UNKNOWN_DEVICE_KEY")
            elif rule.name == "collector_health_ok":
                risk += 2_000
                reasons.append("COLLECTOR_HEALTH_DEGRADED")

        coverage = (valid_weight * 10_000 // expected_weight) if expected_weight else 0
        quality = (weighted_quality // valid_weight) if valid_weight else 0
        risk = max(0, min(10_000, risk))
        if coverage < 10_000:
            reasons.append("SIGNAL_COVERAGE_INCOMPLETE")

        return RiskResult(
            event_id=f"risk:{uuid.uuid4()}",
            score_kind=ScoreKind.HEURISTIC_INDEX,
            risk_bps=risk,
            coverage_bps=coverage,
            quality_bps=quality,
            reason_codes=tuple(dict.fromkeys(reasons)),
            detector_version=self.detector_version,
            evidence_refs=tuple(dict.fromkeys(evidence_refs)),
        )

