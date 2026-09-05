"""Strict token issuance and deterministic pre-verification."""

from __future__ import annotations

import base64
import binascii
import secrets
import time
from dataclasses import replace

from ..canonical import domain_message, sha3_hex
from ..contracts import CryptoEnvelope, Intent
from ..crypto.interfaces import SigningProvider
from ..crypto.registry import SuiteRegistry
from ..errors import ContractError, CryptoError

TOKEN_DOMAIN = "TRQ-BEC/token/v1"
INTENT_DOMAIN = "TRQ-BEC/intent/v1"
DEVICE_PROOF_DOMAIN = "TRQ-BEC/device-proof/v1"


def _b64u_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64u_decode(value: str) -> bytes:
    if not isinstance(value, str) or len(value) > 4096:
        raise ContractError("signature encoding invalid")
    try:
        return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ContractError("signature encoding invalid") from exc


def intent_digest(intent: Intent) -> str:
    return sha3_hex(intent.to_dict(), INTENT_DOMAIN)


def envelope_hash(envelope: CryptoEnvelope) -> str:
    return sha3_hex(envelope.unsigned_dict(), "TRQ-BEC/envelope-hash/v1")


def device_proof_message(
    envelope: CryptoEnvelope,
    challenge: dict[str, str | int],
    session_id: str,
    device_key_id: str,
    operation_jti: str | None = None,
) -> bytes:
    replay_binding = (
        {"token_jti": envelope.jti, "operation_jti": operation_jti}
        if operation_jti is not None
        else {"jti": envelope.jti}
    )
    return domain_message(
        DEVICE_PROOF_DOMAIN,
        {
            "envelope_hash": envelope_hash(envelope),
            **replay_binding,
            "challenge_id": challenge["challenge_id"],
            "random_128": challenge["random_128"],
            "session_id": session_id,
            "device_key_id": device_key_id,
        },
    )


class EnvelopeService:
    def __init__(
        self,
        crypto: SigningProvider,
        suites: SuiteRegistry,
        clock=time.time,
        max_ttl_seconds: int = 120,
        allowed_clock_skew_seconds: int = 5,
    ) -> None:
        self.crypto = crypto
        self.suites = suites
        self.clock = clock
        self.max_ttl_seconds = max_ttl_seconds
        self.allowed_clock_skew_seconds = allowed_clock_skew_seconds

    def issue(
        self,
        intent: Intent,
        *,
        suite_id: str,
        key_id: str,
        policy_version: str,
        issuer: str,
        audience: str,
        ttl_seconds: int = 60,
    ) -> CryptoEnvelope:
        self.suites.require(suite_id)
        if not 1 <= ttl_seconds <= self.max_ttl_seconds:
            raise ContractError("TTL outside policy")
        now = int(self.clock())
        envelope = CryptoEnvelope(
            v=1,
            suite_id=suite_id,
            key_id=key_id,
            policy_version=policy_version,
            iss=issuer,
            aud=audience,
            purpose=intent.purpose,
            iat=now,
            exp=now + ttl_seconds,
            jti=secrets.token_hex(16),
            intent_digest=intent_digest(intent),
        )
        signature = self.crypto.sign(key_id, domain_message(TOKEN_DOMAIN, envelope.unsigned_dict()), "token-signing")
        return replace(envelope, signature=_b64u_encode(signature))

    def verify_preconditions(
        self,
        envelope: CryptoEnvelope,
        expected_intent: Intent,
        *,
        expected_issuer: str,
        expected_audience: str,
        expected_policy_version: str,
    ) -> tuple[bool, tuple[str, ...]]:
        reasons: list[str] = []
        try:
            self.suites.require(envelope.suite_id)
        except CryptoError as exc:
            reasons.append(str(exc))
        if not self.crypto.is_active(envelope.key_id, "token-signing"):
            reasons.append("KEY_INVALID_OR_REVOKED")
        if envelope.iss != expected_issuer:
            reasons.append("ISSUER_MISMATCH")
        if envelope.aud != expected_audience:
            reasons.append("AUDIENCE_MISMATCH")
        if envelope.purpose != expected_intent.purpose:
            reasons.append("PURPOSE_MISMATCH")
        if envelope.policy_version != expected_policy_version:
            reasons.append("POLICY_VERSION_MISMATCH")
        now = int(self.clock())
        skew = self.allowed_clock_skew_seconds
        if envelope.iat > now + skew or now > envelope.exp + skew or envelope.exp - envelope.iat > self.max_ttl_seconds:
            reasons.append("TIME_WINDOW_INVALID")
        if envelope.intent_digest != intent_digest(expected_intent):
            reasons.append("INTENT_MISMATCH")
        try:
            signature = _b64u_decode(envelope.signature)
        except ContractError:
            reasons.append("SIGNATURE_ENCODING_INVALID")
        else:
            if not self.crypto.verify(
                envelope.key_id,
                domain_message(TOKEN_DOMAIN, envelope.unsigned_dict()),
                signature,
                "token-signing",
            ):
                reasons.append("SIGNATURE_INVALID")
        return not reasons, tuple(dict.fromkeys(reasons))

    @staticmethod
    def decode_signature(value: str) -> bytes:
        return _b64u_decode(value)

    @staticmethod
    def encode_signature(value: bytes) -> str:
        return _b64u_encode(value)
