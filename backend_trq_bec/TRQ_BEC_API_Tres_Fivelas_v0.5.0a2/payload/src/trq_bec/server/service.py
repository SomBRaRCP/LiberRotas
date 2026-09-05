"""Authoritative coupon issuance and redemption service."""

from __future__ import annotations

import base64
import secrets
import time
import uuid
from dataclasses import replace
from typing import Any

from ..contracts import CryptoEnvelope, Decision, Intent, Observation, ReplayStatus
from ..crypto.registry import LAB_SUITE_ID
from ..errors import ContractError, CryptoError, LedgerError
from ..policy import PolicyEngine
from ..protocol.envelope import EnvelopeService, device_proof_message
from ..risk import ContextRiskEngine
from .config import ServerSettings
from .models import (
    AuthorizationResponse,
    BeginRedemptionRequest,
    BeginRedemptionResponse,
    ChallengeResponse,
    CompactQrPayload,
    DeviceRecord,
    EnrollDeviceRequest,
    EnrollDeviceResponse,
    HealthResponse,
    IssueCouponRequest,
    IssueCouponResponse,
    OperationRecord,
    Principal,
    TokenRecord,
    AuthorizeRedemptionRequest,
)
from .provider import PostQuantumProvider, verify_device_signature
from .redis_state import DistributedState
from .store import DurableStore, StoreConflict


class ServiceError(RuntimeError):
    def __init__(self, code: str, status_code: int, message: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.message = message or code


class CouponSecurityService:
    def __init__(
        self,
        *,
        settings: ServerSettings,
        store: DurableStore,
        distributed: DistributedState,
        signing_provider,
        pqc_provider: PostQuantumProvider,
        envelopes: EnvelopeService,
        risk: ContextRiskEngine,
        policy: PolicyEngine,
    ) -> None:
        self.settings = settings
        self.store = store
        self.distributed = distributed
        self.signing_provider = signing_provider
        self.pqc_provider = pqc_provider
        self.envelopes = envelopes
        self.risk = risk
        self.policy = policy

    def health(self) -> HealthResponse:
        database_ok = redis_ok = False
        try:
            database_ok = self.store.ping()
        except Exception:
            pass
        try:
            redis_ok = self.distributed.ping()
        except Exception:
            pass
        pq = self.pqc_provider.status()
        return HealthResponse(
            status="ok" if database_ok and redis_ok else "degraded",
            database=database_ok,
            redis=redis_ok,
            crypto_provider=f"{pq.name}:{pq.version}" if pq.ready else "LAB_ED25519_PQ_BLOCKED",
            pqc_ready=pq.ready,
        )

    def _actor_ref(self, uid: str) -> str:
        return self.signing_provider.pseudonymize("actor", uid)

    def _device_ref(self, key_id: str) -> str:
        return self.signing_provider.pseudonymize("device", key_id)

    def _issuer_key_ref(self) -> str:
        return self.signing_provider.key_ref_token(self.settings.issuer_key_id)

    def _append_event(
        self,
        *,
        operation_id: str,
        event_type: str,
        result: str,
        reason_codes: tuple[str, ...] = (),
        evidence_refs: tuple[str, ...] = (),
        details: dict[str, Any] | None = None,
    ):
        return self.store.append_audit(
            operation_id=operation_id,
            suite_id=LAB_SUITE_ID,
            key_ref_token=self._issuer_key_ref(),
            event_type=event_type,
            result=result,
            reason_codes=reason_codes,
            evidence_refs=evidence_refs,
            details=details or {},
        )

    def enroll_device(self, principal: Principal, request: EnrollDeviceRequest) -> EnrollDeviceResponse:
        try:
            device, created = self.store.enroll_device(
                principal.uid,
                request.device_key_id,
                request.public_key_b64u,
                request.algorithm,
                request.storage_profile,
            )
        except StoreConflict as exc:
            raise ServiceError(str(exc), 409) from exc
        event = self._append_event(
            operation_id=f"enroll:{uuid.uuid4()}",
            event_type="DEVICE_ENROLLMENT",
            result="ENROLLED" if created else "ALREADY_ENROLLED",
            details={
                "actor_ref": self._actor_ref(principal.uid),
                "device_ref": self._device_ref(request.device_key_id),
                "algorithm": request.algorithm,
            },
        )
        return EnrollDeviceResponse(
            device_key_id=device.device_key_id,
            status="ENROLLED" if created else "ALREADY_ENROLLED",
            key_ref=self._device_ref(device.device_key_id),
        )

    def issue_coupon(self, principal: Principal, request: IssueCouponRequest) -> IssueCouponResponse:
        if not principal.is_entrepreneur:
            raise ServiceError("ENTREPRENEUR_CLAIM_REQUIRED", 403)
        if request.issuer_id != principal.uid:
            raise ServiceError("ISSUER_BINDING_MISMATCH", 403)
        if self.store.get_device(principal.uid, request.device_key_id) is None:
            raise ServiceError("DEVICE_NOT_ENROLLED", 403)
        coupon = self.store.get_coupon_for_issue(request.coupon_id, principal.uid)
        if coupon is None:
            raise ServiceError("COUPON_NOT_ACTIVE_OR_NOT_OWNED", 404)
        if not self.settings.lab_suite_enabled:
            pq = self.pqc_provider.status()
            if not pq.ready:
                raise ServiceError("PQC_PROVIDER_NOT_READY", 503)
            raise ServiceError("PQC_ENVELOPE_ADAPTER_PENDING_APPROVAL", 503)

        now = int(time.time())
        intent = Intent(
            txn_id=f"coupon:{uuid.uuid4()}",
            merchant_id=principal.uid,
            amount_minor=1,
            currency="BRL",
            resource_ref=f"coupon/{request.coupon_id}",
            purpose="LIBERROTAS_COUPON_REDEEM",
        )
        envelope = self.envelopes.issue(
            intent,
            suite_id=LAB_SUITE_ID,
            key_id=self.settings.issuer_key_id,
            policy_version=self.settings.policy_version,
            issuer=self.settings.issuer,
            audience=self.settings.audience,
            ttl_seconds=self.settings.token_ttl_seconds,
        )
        token_ref = secrets.token_urlsafe(24)
        issuer_ref = self._actor_ref(principal.uid)
        record = TokenRecord(
            token_ref=token_ref,
            issuer_uid=principal.uid,
            issuer_ref=issuer_ref,
            coupon_id=request.coupon_id,
            intent=intent.to_dict(),
            envelope=envelope.to_dict(),
            expires_at=envelope.exp,
            status="ISSUED",
            redeemed_operation_id=None,
        )
        self.store.store_token(record)
        self._append_event(
            operation_id=f"issue:{uuid.uuid4()}",
            event_type="COUPON_ISSUED",
            result="ISSUED",
            details={
                "actor_ref": issuer_ref,
                "coupon_id": request.coupon_id,
                "expires_at": envelope.exp,
            },
        )
        qr = CompactQrPayload(
            token_ref=token_ref,
            issuer_ref=issuer_ref,
            expires_at=envelope.exp,
        )
        return IssueCouponResponse(qr_payload=qr, expires_at=envelope.exp)

    def _load_valid_token(self, payload: CompactQrPayload) -> TokenRecord:
        token = self.store.get_token(payload.token_ref)
        if token is None:
            raise ServiceError("TOKEN_REFERENCE_UNKNOWN", 404)
        if token.issuer_ref != payload.issuer_ref or token.expires_at != payload.expires_at:
            raise ServiceError("QR_BINDING_MISMATCH", 400)
        if token.status != "ISSUED":
            raise ServiceError("TOKEN_NOT_REDEEMABLE", 409)
        if int(time.time()) > token.expires_at:
            raise ServiceError("TOKEN_EXPIRED", 410)
        intent = Intent.from_dict(token.intent)
        envelope = CryptoEnvelope.from_dict(token.envelope)
        ok, reasons = self.envelopes.verify_preconditions(
            envelope,
            intent,
            expected_issuer=self.settings.issuer,
            expected_audience=self.settings.audience,
            expected_policy_version=self.settings.policy_version,
        )
        if not ok:
            raise ServiceError(f"TOKEN_CRYPTO_INVALID:{','.join(reasons)}", 400, "TOKEN_CRYPTO_INVALID")
        return token

    def begin_redemption(self, principal: Principal, request: BeginRedemptionRequest) -> BeginRedemptionResponse:
        token = self._load_valid_token(request.qr_payload)
        device = self.store.get_device(principal.uid, request.device_key_id)
        if device is None:
            raise ServiceError("DEVICE_NOT_ENROLLED", 403)
        operation_id = f"op:{uuid.uuid4()}"
        session_id = f"session:{uuid.uuid4()}"
        challenge = self.distributed.issue_challenge(operation_id, self.settings.challenge_ttl_seconds)
        operation = OperationRecord(
            operation_id=operation_id,
            firebase_uid=principal.uid,
            session_id=session_id,
            token_ref=token.token_ref,
            device_key_id=device.device_key_id,
            challenge_id=str(challenge["challenge_id"]),
            expires_at=min(int(challenge["expires_at"]), int(time.time()) + self.settings.operation_ttl_seconds),
            status="PENDING",
            result=None,
        )
        try:
            self.store.create_operation(operation)
        except Exception:
            self.distributed.consume_challenge(str(challenge["challenge_id"]), operation_id)
            raise
        envelope = CryptoEnvelope.from_dict(token.envelope)
        proof_message = device_proof_message(envelope, challenge, session_id, device.device_key_id)
        self._append_event(
            operation_id=operation_id,
            event_type="REDEMPTION_BEGUN",
            result="PENDING",
            details={
                "actor_ref": self._actor_ref(principal.uid),
                "device_ref": self._device_ref(device.device_key_id),
                "coupon_id": token.coupon_id,
            },
        )
        return BeginRedemptionResponse(
            operation_id=operation_id,
            session_id=session_id,
            challenge=ChallengeResponse(
                challenge_id=str(challenge["challenge_id"]),
                expires_at=int(challenge["expires_at"]),
            ),
            proof_message_b64u=base64.urlsafe_b64encode(proof_message).rstrip(b"=").decode("ascii"),
        )

    def _deny(
        self,
        operation_id: str,
        code: str,
        *,
        crypto_ok: bool = False,
        coupon_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuthorizationResponse:
        event_ref = None
        try:
            event = self._append_event(
                operation_id=operation_id,
                event_type="REDEMPTION_AUTHORIZATION",
                result="DENY",
                reason_codes=(code,),
                details=details or {},
            )
            event_ref = event.event_id
        except LedgerError:
            pass
        return AuthorizationResponse(
            decision="DENY",
            operation_id=operation_id,
            crypto_ok=crypto_ok,
            reason_codes=[code],
            coupon_id=coupon_id,
            event_ref=event_ref,
        )

    def authorize_redemption(
        self,
        principal: Principal,
        request: AuthorizeRedemptionRequest,
    ) -> AuthorizationResponse:
        operation = self.store.get_operation(request.operation_id)
        if operation is None:
            raise ServiceError("OPERATION_UNKNOWN", 404)
        if operation.status != "PENDING" and operation.result:
            prior = AuthorizationResponse.model_validate(operation.result)
            return prior.model_copy(update={"idempotent": True})
        if int(time.time()) > operation.expires_at:
            return self._deny(request.operation_id, "OPERATION_EXPIRED")
        if (
            operation.firebase_uid != principal.uid
            or operation.session_id != request.session_id
            or operation.device_key_id != request.device_key_id
            or operation.challenge_id != request.challenge_id
        ):
            return self._deny(request.operation_id, "OPERATION_BINDING_MISMATCH")

        token = self.store.get_token(operation.token_ref)
        device = self.store.get_device(principal.uid, request.device_key_id)
        if token is None or device is None:
            return self._deny(request.operation_id, "TOKEN_OR_DEVICE_UNAVAILABLE")
        envelope = CryptoEnvelope.from_dict(token.envelope)
        intent = Intent.from_dict(token.intent)
        crypto_ok, crypto_reasons = self.envelopes.verify_preconditions(
            envelope,
            intent,
            expected_issuer=self.settings.issuer,
            expected_audience=self.settings.audience,
            expected_policy_version=self.settings.policy_version,
        )
        if not crypto_ok:
            return self._deny(request.operation_id, crypto_reasons[0] if crypto_reasons else "CRYPTO_INVALID")

        try:
            replay = self.distributed.reserve_replay(
                envelope.iss,
                envelope.jti,
                request.operation_id,
                self.settings.replay_ttl_seconds,
            )
        except Exception as exc:
            raise ServiceError("REPLAY_STORE_UNAVAILABLE", 503) from exc
        if replay is ReplayStatus.REPLAY:
            return self._deny(request.operation_id, "REPLAY", coupon_id=token.coupon_id)
        if replay is ReplayStatus.SAME_OP:
            cached = self.distributed.get_replay_result(envelope.iss, envelope.jti, request.operation_id)
            if cached:
                prior = AuthorizationResponse.model_validate(cached)
                return prior.model_copy(update={"idempotent": True})
            return self._deny(request.operation_id, "INCOMPLETE_PRIOR_OPERATION")

        challenge = self.distributed.get_challenge(request.challenge_id, request.operation_id)
        if challenge is None:
            self.distributed.abort_replay(envelope.iss, envelope.jti, request.operation_id)
            return self._deny(request.operation_id, "FRESHNESS_CHALLENGE_INVALID")
        proof_message = device_proof_message(envelope, challenge, request.session_id, request.device_key_id)
        if not verify_device_signature(device.public_key_b64u, proof_message, request.device_proof_b64u):
            self.distributed.abort_replay(envelope.iss, envelope.jti, request.operation_id)
            return self._deny(request.operation_id, "DEVICE_PROOF_INVALID")
        if not self.distributed.consume_challenge(request.challenge_id, request.operation_id):
            self.distributed.abort_replay(envelope.iss, envelope.jti, request.operation_id)
            return self._deny(request.operation_id, "FRESHNESS_CONSUME_FAILED")

        now = int(time.time())
        actor_ref = self._actor_ref(principal.uid)
        device_ref = self._device_ref(request.device_key_id)
        rate_high = self.distributed.rate_is_high(
            actor_ref,
            self.settings.rate_window_seconds,
            self.settings.rate_high_threshold,
        )
        observations = [
            Observation("device_key_known", "true", "firebase-backend", now, now + 30, 10_000, 10_000, f"evidence:{device_ref}"),
            Observation("session_context_changed", "false", "firebase-backend", now, now + 30, 9_000, 10_000, f"evidence:session:{request.operation_id}"),
            Observation("rate_increase", str(rate_high).lower(), "firebase-backend", now, now + 30, 9_000, 10_000, f"evidence:rate:{request.operation_id}"),
            Observation("collector_health_ok", "true", "firebase-backend", now, now + 30, 10_000, 10_000, f"evidence:health:{request.operation_id}"),
        ]
        risk_result = self.risk.evaluate(observations)
        decision = self.policy.decide(True, risk_result)
        response = AuthorizationResponse(
            decision=decision.value,
            operation_id=request.operation_id,
            crypto_ok=True,
            reason_codes=list(risk_result.reason_codes),
            coupon_id=token.coupon_id if decision is Decision.ALLOW else None,
        )
        try:
            event = self.store.finalize_authorization(
                request.operation_id,
                token.token_ref,
                decision.value,
                response.model_dump(mode="json"),
                suite_id=envelope.suite_id,
                key_ref_token=self._issuer_key_ref(),
                event_type="REDEMPTION_AUTHORIZATION",
                reason_codes=risk_result.reason_codes,
                evidence_refs=risk_result.evidence_refs,
                details={
                    "actor_ref": actor_ref,
                    "device_ref": device_ref,
                    "coupon_id": token.coupon_id,
                    "risk_bps": risk_result.risk_bps,
                    "coverage_bps": risk_result.coverage_bps,
                    "detector_version": risk_result.detector_version,
                },
            )
        except StoreConflict as exc:
            self.distributed.abort_replay(envelope.iss, envelope.jti, request.operation_id)
            return self._deny(request.operation_id, str(exc), coupon_id=token.coupon_id)
        response = response.model_copy(update={"event_ref": event.event_id})
        committed = self.distributed.commit_replay(
            envelope.iss,
            envelope.jti,
            request.operation_id,
            response.model_dump(mode="json"),
            self.settings.replay_ttl_seconds,
        )
        if not committed:
            response = response.model_copy(
                update={"reason_codes": [*response.reason_codes, "REPLAY_CACHE_COMMIT_DEGRADED"]}
            )
        return response

    def checkpoint(self, principal: Principal) -> dict[str, Any]:
        if not principal.is_admin:
            raise ServiceError("ADMIN_CLAIM_REQUIRED", 403)
        try:
            return self.store.create_checkpoint(self.settings.checkpoint_key_id, self.settings.policy_version)
        except LedgerError as exc:
            raise ServiceError(str(exc), 409) from exc
