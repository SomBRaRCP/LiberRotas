"""Deterministic stand-in for the future AI Assurance Layer.

Its constructor deliberately receives neither crypto provider nor policy engine.
It can synthesize a recommendation but has no execution method.
"""

from __future__ import annotations

import uuid

from ..contracts import AuditRecommendation, Decision, RiskResult
from ..ledger.ledger import LedgerEvent

ALLOWED_ACTIONS = {"OBSERVE", "STEP_UP", "HOLD", "REVIEW", "PLAN_ROTATION"}


class AssuranceObserver:
    def recommend(
        self,
        *,
        decision: Decision,
        policy_version: str,
        risk: RiskResult,
        events: tuple[LedgerEvent, ...],
    ) -> AuditRecommendation:
        if decision is Decision.HOLD_OR_REVIEW:
            action, severity = "REVIEW", "HIGH"
        elif decision is Decision.STEP_UP:
            action, severity = "STEP_UP", "MEDIUM"
        else:
            action, severity = "OBSERVE", "LOW"
        assert action in ALLOWED_ACTIONS
        refs = tuple(event.event_id for event in events[-5:]) + risk.evidence_refs
        confidence = min(risk.coverage_bps, risk.quality_bps)
        return AuditRecommendation(
            finding_id=f"finding:{uuid.uuid4()}",
            severity=severity,
            proposed_action=action,
            reviewer_state="PENDING" if action != "OBSERVE" else "NOT_REQUIRED",
            policy_version=policy_version,
            evidence_refs=tuple(dict.fromkeys(refs)),
            reason_codes=risk.reason_codes,
            confidence_bps=confidence,
        )

