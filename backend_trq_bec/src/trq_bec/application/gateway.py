"""Five-gate TRQ-BEC authorization flow."""

from __future__ import annotations

import threading
import time
from dataclasses import replace
from pathlib import Path

from ..assurance import AssuranceObserver
from ..contracts import AuthorizationResult, CryptoEnvelope, Decision, Intent, Observation, ReplayStatus
from ..crypto import DevelopmentCryptoProvider, LAB_SUITE_ID, SuiteRegistry
from ..errors import ContractError, LedgerError
from ..ledger import EvidenceLedger
from ..policy import Policy, PolicyEngine
from ..protocol import ChallengeStore, EnvelopeService, InMemoryReplayStore
from ..protocol.envelope import device_proof_message
from ..risk import ContextRiskEngine


class TRQBECGateway:
    """Coordinates components without allowing authority to flow backwards."""

    def __init__(
        self,
        *,
        crypto: DevelopmentCryptoProvider,
        envelopes: EnvelopeService,
        challenges: ChallengeStore,
        replay: InMemoryReplayStore,
        risk: ContextRiskEngine,
        policy: PolicyEngine,
        ledger: EvidenceLedger,
        assurance: AssuranceObserver,
        issuer: str,
        audience: str,
        issuer_key_id: str,
    ) -> None:
        self.crypto = crypto
        self.envelopes = envelopes
        self.challenges = challenges
        self.replay = replay
        self.risk = risk
        self.policy = policy
        self.ledger = ledger
        self.assurance = assurance
        self.issuer = issuer
        self.audience = audience
        self.issuer_key_id = issuer_key_id
        self._results: dict[tuple[str, str, str], AuthorizationResult] = {}
        self._result_lock = threading.Lock()

    def issue_token(self, intent: Intent, ttl_seconds: int = 60) -> CryptoEnvelope:
        return self.envelopes.issue(
            intent,
            suite_id=LAB_SUITE_ID,
            key_id=self.issuer_key_id,
            policy_version=self.policy.policy.version,
            issuer=self.issuer,
            audience=self.audience,
            ttl_seconds=ttl_seconds,
        )

    def issue_challenge(self, operation_id: str):
        return self.challenges.issue(operation_id)

    def create_device_key(self, device_key_id: str) -> None:
        """Laboratory enrollment; production enrollment must attest device keys."""
        self.crypto.generate_signing_key(device_key_id, "device-proof")

    def sign_device_proof(
        self,
        envelope: CryptoEnvelope,
        challenge_id: str,
        operation_id: str,
        session_id: str,
        device_key_id: str,
    ) -> str:
        """Lab client helper; not part of a production server API."""
        challenge = self.challenges.peek(challenge_id, operation_id)
        if challenge is None:
            raise ContractError("challenge is unavailable")
        proof = self.crypto.sign(
            device_key_id,
            device_proof_message(envelope, challenge.to_dict(), session_id, device_key_id),
            "device-proof",
        )
        return self.envelopes.encode_signature(proof)

    def _deny_event(
        self,
        envelope: CryptoEnvelope,
        operation_id: str,
        reasons: tuple[str, ...],
    ) -> AuthorizationResult:
        try:
            event = self.ledger.append(
                operation_id=operation_id,
                suite_id=envelope.suite_id,
                key_ref_token=self.crypto.key_ref_token(envelope.key_id),
                event_type="AUTHORIZATION",
                result=Decision.DENY.value,
                reason_codes=reasons,
            )
            refs = (event.event_id,)
        except LedgerError:
            refs = ()
        return AuthorizationResult(Decision.DENY, operation_id, False, reasons, event_refs=refs)

    def authorize(
        self,
        *,
        envelope: CryptoEnvelope,
        expected_intent: Intent,
        operation_id: str,
        session_id: str,
        device_key_id: str,
        challenge_id: str,
        device_proof_b64u: str,
        observations: list[Observation],
        step_up_passed: bool = False,
    ) -> AuthorizationResult:
        crypto_ok, reasons = self.envelopes.verify_preconditions(
            envelope,
            expected_intent,
            expected_issuer=self.issuer,
            expected_audience=self.audience,
            expected_policy_version=self.policy.policy.version,
        )
        if not crypto_ok:
            return self._deny_event(envelope, operation_id, reasons)

        replay_status = self.replay.reserve(envelope.iss, envelope.jti, operation_id)
        if replay_status is ReplayStatus.REPLAY:
            return self._deny_event(envelope, operation_id, ("REPLAY",))
        if replay_status is ReplayStatus.SAME_OP:
            with self._result_lock:
                prior = self._results.get((envelope.iss, envelope.jti, operation_id))
            if prior is not None:
                return replace(prior, idempotent=True)
            self.replay.abort(envelope.iss, envelope.jti, operation_id)
            return self._deny_event(envelope, operation_id, ("INCOMPLETE_PRIOR_OPERATION",))

        challenge = self.challenges.peek(challenge_id, operation_id)
        if challenge is None:
            self.replay.abort(envelope.iss, envelope.jti, operation_id)
            return self._deny_event(envelope, operation_id, ("FRESHNESS_CHALLENGE_INVALID",))
        try:
            proof = self.envelopes.decode_signature(device_proof_b64u)
        except ContractError:
            proof = b""
        proof_ok = self.crypto.verify(
            device_key_id,
            device_proof_message(envelope, challenge.to_dict(), session_id, device_key_id),
            proof,
            "device-proof",
        )
        if not proof_ok or not self.challenges.consume(challenge_id, operation_id):
            self.replay.abort(envelope.iss, envelope.jti, operation_id)
            return self._deny_event(envelope, operation_id, ("DEVICE_PROOF_OR_FRESHNESS_INVALID",))

        risk_result = self.risk.evaluate(observations)
        decision = self.policy.decide(True, risk_result, step_up_passed)
        try:
            event = self.ledger.append(
                operation_id=operation_id,
                suite_id=envelope.suite_id,
                key_ref_token=self.crypto.key_ref_token(envelope.key_id),
                event_type="AUTHORIZATION",
                result=decision.value,
                reason_codes=risk_result.reason_codes,
                evidence_refs=risk_result.evidence_refs,
            )
        except LedgerError:
            self.replay.abort(envelope.iss, envelope.jti, operation_id)
            return AuthorizationResult(
                Decision.DENY,
                operation_id,
                False,
                ("EVIDENCE_LEDGER_UNAVAILABLE",),
            )

        recommendation = self.assurance.recommend(
            decision=decision,
            policy_version=self.policy.policy.version,
            risk=risk_result,
            events=self.ledger.events,
        )
        if not self.replay.commit(envelope.iss, envelope.jti, operation_id):
            return self._deny_event(envelope, operation_id, ("REPLAY_COMMIT_FAILED",))

        result = AuthorizationResult(
            decision=decision,
            operation_id=operation_id,
            crypto_ok=True,
            reason_codes=risk_result.reason_codes,
            risk=risk_result,
            recommendation=recommendation,
            event_refs=(event.event_id,),
        )
        with self._result_lock:
            self._results[(envelope.iss, envelope.jti, operation_id)] = result
        return result


def build_lab_gateway(ledger_path: Path | None = None, clock=time.time) -> TRQBECGateway:
    crypto = DevelopmentCryptoProvider()
    issuer_key_id = "issuer-lab-2026-01"
    crypto.generate_signing_key(issuer_key_id, "token-signing")
    crypto.generate_signing_key("checkpoint-lab-2026-01", "checkpoint-signing")
    policy = PolicyEngine(
        Policy(
            version="liberrotas-lab-policy-1",
            q_min_bps=7_000,
            low_risk_bps=3_500,
            high_risk_bps=7_000,
        )
    )
    suites = SuiteRegistry({LAB_SUITE_ID})
    return TRQBECGateway(
        crypto=crypto,
        envelopes=EnvelopeService(crypto, suites, clock=clock),
        challenges=ChallengeStore(clock=clock),
        replay=InMemoryReplayStore(),
        risk=ContextRiskEngine({"liberrotas-app", "firebase-backend"}, clock=clock),
        policy=policy,
        ledger=EvidenceLedger(ledger_path, clock=clock),
        assurance=AssuranceObserver(),
        issuer="trq-bec.liberrotas.local",
        audience="app-liberrotas",
        issuer_key_id=issuer_key_id,
    )

