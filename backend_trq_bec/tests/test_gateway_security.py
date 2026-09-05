from __future__ import annotations

import uuid
import unittest
from dataclasses import replace

from trq_bec.contracts import Decision

from helpers import make_intent, observations, prepared_flow


def authorize(flow, *, envelope=None, intent=None, proof=None, obs=None):
    gateway, device_key_id, original_intent, original_envelope, operation_id, session_id, challenge, original_proof = flow
    return gateway.authorize(
        envelope=envelope or original_envelope,
        expected_intent=intent or original_intent,
        operation_id=operation_id,
        session_id=session_id,
        device_key_id=device_key_id,
        challenge_id=challenge.challenge_id,
        device_proof_b64u=proof if proof is not None else original_proof,
        observations=obs if obs is not None else observations("low"),
    )


class GatewaySecurityTests(unittest.TestCase):
    def test_valid_low_risk_flow_allows(self) -> None:
        flow = prepared_flow()
        result = authorize(flow)
        self.assertEqual(result.decision, Decision.ALLOW)
        self.assertTrue(result.crypto_ok)
        self.assertTrue(flow[0].ledger.verify())

    def test_tampered_envelope_is_denied(self) -> None:
        flow = prepared_flow()
        tampered = replace(flow[3], aud="evil")
        result = authorize(flow, envelope=tampered)
        self.assertEqual(result.decision, Decision.DENY)
        self.assertIn("AUDIENCE_MISMATCH", result.reason_codes)
        self.assertIn("SIGNATURE_INVALID", result.reason_codes)

    def test_authoritative_intent_mismatch_is_denied(self) -> None:
        flow = prepared_flow()
        result = authorize(flow, intent=make_intent(9999))
        self.assertEqual(result.decision, Decision.DENY)
        self.assertIn("INTENT_MISMATCH", result.reason_codes)

    def test_unknown_suite_downgrade_fails_closed(self) -> None:
        flow = prepared_flow()
        token = replace(flow[3], suite_id="none")
        result = authorize(flow, envelope=token)
        self.assertEqual(result.decision, Decision.DENY)
        self.assertIn("SUITE_NOT_ALLOWED", result.reason_codes)

    def test_revoked_issuer_key_is_denied(self) -> None:
        flow = prepared_flow()
        flow[0].crypto.revoke(flow[3].key_id)
        result = authorize(flow)
        self.assertEqual(result.decision, Decision.DENY)
        self.assertIn("KEY_INVALID_OR_REVOKED", result.reason_codes)

    def test_invalid_device_proof_is_denied(self) -> None:
        flow = prepared_flow()
        result = authorize(flow, proof="AA")
        self.assertEqual(result.decision, Decision.DENY)
        self.assertIn("DEVICE_PROOF_OR_FRESHNESS_INVALID", result.reason_codes)

    def test_exact_operation_retry_is_idempotent(self) -> None:
        flow = prepared_flow()
        first = authorize(flow)
        second = authorize(flow)
        self.assertEqual(first.decision, second.decision)
        self.assertTrue(second.idempotent)
        self.assertEqual(len(flow[0].ledger.events), 1)

    def test_same_token_different_operation_is_replay(self) -> None:
        flow = prepared_flow()
        first = authorize(flow)
        self.assertEqual(first.decision, Decision.ALLOW)
        gateway, device_key_id, intent, envelope, _, _, _, _ = flow
        operation_id = f"op:{uuid.uuid4()}"
        session_id = f"session:{uuid.uuid4()}"
        challenge = gateway.issue_challenge(operation_id)
        proof = gateway.sign_device_proof(envelope, challenge.challenge_id, operation_id, session_id, device_key_id)
        second = gateway.authorize(
            envelope=envelope,
            expected_intent=intent,
            operation_id=operation_id,
            session_id=session_id,
            device_key_id=device_key_id,
            challenge_id=challenge.challenge_id,
            device_proof_b64u=proof,
            observations=observations("low"),
        )
        self.assertEqual(second.decision, Decision.DENY)
        self.assertIn("REPLAY", second.reason_codes)
        self.assertEqual(gateway.replay.committed_count(envelope.iss, envelope.jti), 1)

    def test_incomplete_context_requires_step_up(self) -> None:
        flow = prepared_flow()
        result = authorize(flow, obs=observations("low")[:1])
        self.assertEqual(result.decision, Decision.STEP_UP)
        self.assertTrue(result.crypto_ok)

    def test_high_risk_valid_crypto_holds_for_review(self) -> None:
        flow = prepared_flow()
        result = authorize(flow, obs=observations("high"))
        self.assertEqual(result.decision, Decision.HOLD_OR_REVIEW)
        self.assertTrue(result.crypto_ok)
        self.assertEqual(result.recommendation.proposed_action, "REVIEW")


if __name__ == "__main__":
    unittest.main()
