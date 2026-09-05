from __future__ import annotations

import base64
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from trq_bec.crypto import DevelopmentCryptoProvider, LAB_SUITE_ID, SuiteRegistry
from trq_bec.policy import Policy, PolicyEngine
from trq_bec.protocol import EnvelopeService
from trq_bec.risk import ContextRiskEngine
from trq_bec.server.access_control import default_permissions
from trq_bec.server.config import ServerSettings
from trq_bec.server.memory_store import MemoryDurableStore
from trq_bec.server.models import (
    AccessAccountRecord,
    AuthorizeRedemptionRequest,
    BeginRedemptionRequest,
    EnrollDeviceRequest,
    IssueCouponRequest,
    MerchantStatusRequest,
    Principal,
    PrivilegedAccountValidationRecord,
    ProductCreateRequest,
    OfferStatusRequest,
    PreviewCouponRequest,
)
from trq_bec.server.provider import UnavailablePQCProvider
from trq_bec.server.redis_state import MemoryDistributedState
from trq_bec.server.service import CouponSecurityService, ServiceError


def b64u(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


class FailingReplayState(MemoryDistributedState):
    def reserve_replay(self, issuer: str, jti: str, operation_id: str, ttl_seconds: int):
        raise ConnectionError("redis unavailable")


class FailingChallengeReadState(MemoryDistributedState):
    def get_challenge(self, challenge_id: str, operation_id: str):
        raise ConnectionError("redis unavailable")


class FailingRateState(MemoryDistributedState):
    def rate_is_high(self, subject_ref: str, window_seconds: int, threshold: int):
        raise ConnectionError("redis unavailable")


class FailingCommitState(MemoryDistributedState):
    def commit_replay(self, issuer: str, jti: str, operation_id: str, result: dict, ttl_seconds: int):
        raise ConnectionError("redis unavailable")


class MarketplacePhase1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = ServerSettings(environment="test", policy_version="phase1-test-policy")
        self.crypto = DevelopmentCryptoProvider()
        self.crypto.generate_signing_key(self.settings.issuer_key_id, "token-signing")
        self.crypto.generate_signing_key(self.settings.checkpoint_key_id, "checkpoint-signing")
        self.store = MemoryDurableStore(self.crypto)
        self.distributed = MemoryDistributedState()
        self.service = self._service(self.distributed)
        self.admin = Principal("admin-uid", "admin", None, {"role": "admin", "admin": True})
        self.store.set_access_account(
            AccessAccountRecord(
                self.admin.uid,
                None,
                "admin",
                "ACTIVE",
                False,
                default_permissions("admin"),
            )
        )
        validated_at = datetime.now(timezone.utc)
        self.store.set_privileged_account_validation(
            PrivilegedAccountValidationRecord(
                firebase_uid=self.admin.uid,
                requested_role="admin",
                validation_state="APPROVED",
                protection_level="SYSTEM",
                account_origin="BOOTSTRAP",
                created_by_uid="system:test-bootstrap",
                validated_by_uid="system:test-bootstrap",
                validation_reason="Administrador oficial validado para o cenário de teste.",
                validated_at=validated_at,
                created_at=validated_at,
                updated_at=validated_at,
            )
        )
        self.merchant = Principal(
            "merchant-uid",
            "entrepreneur",
            None,
            {"role": "entrepreneur", "auth_time": int(time.time())},
        )
        self.merchant_key = Ed25519PrivateKey.generate()
        self.service.set_merchant_status(
            self.admin,
            MerchantStatusRequest(
                firebase_uid=self.merchant.uid,
                display_name="Artesã da Feira",
                establishment_id="EST-PINHAIS-01",
                establishment_name="Feira LiberRotas",
                status="ACTIVE",
            ),
        )
        self._enroll(self.service, self.merchant, "device:merchant-test", self.merchant_key)

    def _service(self, distributed: MemoryDistributedState) -> CouponSecurityService:
        return CouponSecurityService(
            settings=self.settings,
            store=self.store,
            distributed=distributed,
            signing_provider=self.crypto,
            pqc_provider=UnavailablePQCProvider(),
            envelopes=EnvelopeService(
                self.crypto,
                SuiteRegistry({LAB_SUITE_ID}),
                max_ttl_seconds=self.settings.live_offer_max_ttl_seconds,
            ),
            risk=ContextRiskEngine({"firebase-backend"}),
            policy=PolicyEngine(Policy("phase1-test-policy", 7_000, 3_500, 7_000)),
        )

    @staticmethod
    def _enroll(
        service: CouponSecurityService,
        principal: Principal,
        device_key_id: str,
        private_key: Ed25519PrivateKey,
    ) -> None:
        if service.store.get_access_account(principal.uid) is None and principal.role == "visitor":
            service.store.set_access_account(
                AccessAccountRecord(
                    principal.uid,
                    principal.email,
                    "visitor",
                    "ACTIVE",
                    False,
                    default_permissions("visitor"),
                )
            )
        enrollment = service.enroll_device(
            principal,
            EnrollDeviceRequest(
                device_key_id=device_key_id,
                public_key_b64u=b64u(private_key.public_key().public_bytes_raw()),
                algorithm="ED25519_LAB",
                storage_profile="EXPO_SECURE_STORE_LAB",
            ),
        )
        if enrollment.device_status == "PENDING_APPROVAL":
            current = service.store.devices[device_key_id]
            service.store.devices[device_key_id] = replace(
                current,
                approval_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
            )
            service.list_account_devices(principal)

    def _product(self, *, price_minor: int = 5_000, stock: int = 10):
        return self.service.create_product(
            self.merchant,
            ProductCreateRequest(
                title="Bordado artesanal",
                description="Peça autoral",
                price_minor=price_minor,
                currency="BRL",
                stock_quantity=stock,
            ),
        )

    def _issue(self, product_id: str, *, maximum: int = 10):
        return self.service.issue_coupon(
            self.merchant,
            IssueCouponRequest(
                product_id=product_id,
                discount_type="PERCENT",
                discount_value=20,
                maximum_redemptions=maximum,
                valid_until=datetime.now(timezone.utc) + timedelta(minutes=5),
                purpose="LIVE_FAIR_DISCOUNT",
                device_key_id="device:merchant-test",
            ),
        )

    def _prepare_authorization(self, index: int, qr_payload, service: CouponSecurityService | None = None):
        service = service or self.service
        principal = Principal(
            f"buyer-{index}",
            "visitor",
            None,
            {"role": "visitor", "auth_time": int(time.time())},
        )
        private_key = Ed25519PrivateKey.generate()
        device_key_id = f"device:buyer-{index:03d}"
        self._enroll(service, principal, device_key_id, private_key)
        begin = service.begin_redemption(
            principal,
            BeginRedemptionRequest(qr_payload=qr_payload, device_key_id=device_key_id),
        )
        proof = private_key.sign(base64.urlsafe_b64decode(begin.proof_message_b64u + "=" * (-len(begin.proof_message_b64u) % 4)))
        request = AuthorizeRedemptionRequest(
            operation_id=begin.operation_id,
            session_id=begin.session_id,
            challenge_id=begin.challenge.challenge_id,
            device_key_id=device_key_id,
            device_proof_b64u=b64u(proof),
        )
        return principal, request

    def test_backend_calculates_price_and_rejects_client_price_fields(self) -> None:
        product = self._product(price_minor=5_000)
        issued = self._issue(product.product_id)
        self.assertEqual(issued.offer.original_amount_minor, 5_000)
        self.assertEqual(issued.offer.discount_amount_minor, 1_000)
        self.assertEqual(issued.offer.final_amount_minor, 4_000)
        with self.assertRaises(ValidationError):
            IssueCouponRequest.model_validate(
                {
                    "product_id": product.product_id,
                    "discount_type": "PERCENT",
                    "discount_value": 20,
                    "maximum_redemptions": 1,
                    "valid_until": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
                    "purpose": "LIVE_FAIR_DISCOUNT",
                    "device_key_id": "device:merchant-test",
                    "final_amount_minor": 1,
                }
            )

    def test_suspended_merchant_cannot_issue(self) -> None:
        product = self._product()
        self.service.set_merchant_status(
            self.admin,
            MerchantStatusRequest(
                firebase_uid=self.merchant.uid,
                display_name="Artesã da Feira",
                establishment_id="EST-PINHAIS-01",
                establishment_name="Feira LiberRotas",
                status="SUSPENDED",
            ),
        )
        with self.assertRaisesRegex(ServiceError, "ACCOUNT_SUSPENDED"):
            self._issue(product.product_id)

    def test_additional_device_is_pending_and_cannot_sign_operations(self) -> None:
        additional_key = Ed25519PrivateKey.generate()
        response = self.service.enroll_device(
            self.merchant,
            EnrollDeviceRequest(
                device_key_id="device:merchant-additional",
                public_key_b64u=b64u(additional_key.public_key().public_bytes_raw()),
                algorithm="ED25519_LAB",
                storage_profile="EXPO_SECURE_STORE_LAB",
            ),
        )
        self.assertEqual(response.device_status, "PENDING_APPROVAL")
        self.assertTrue(response.is_additional_device)
        self.assertEqual(response.notification_status, "NOT_CONFIGURED")
        self.assertIsNone(
            self.store.get_device("merchant-uid", "device:merchant-additional")
        )

    def test_existing_device_enrollment_remains_idempotent_after_auth_window(self) -> None:
        private_key = Ed25519PrivateKey.generate()
        fresh = Principal(
            "returning-uid",
            "visitor",
            None,
            {"role": "visitor", "auth_time": int(time.time())},
        )
        self._enroll(self.service, fresh, "device:returning-user", private_key)
        stale = replace(
            fresh,
            claims={"role": "visitor", "auth_time": int(time.time()) - 86_400},
        )
        self._enroll(self.service, stale, "device:returning-user", private_key)

    def test_suspended_merchant_is_blocked_before_preview_or_challenge(self) -> None:
        issued = self._issue(self._product().product_id)
        self.service.set_merchant_status(
            self.admin,
            MerchantStatusRequest(
                firebase_uid=self.merchant.uid,
                display_name="Artesã da Feira",
                establishment_id="EST-PINHAIS-01",
                establishment_name="Feira LiberRotas",
                status="SUSPENDED",
            ),
        )
        buyer = Principal(
            "buyer-suspended",
            "visitor",
            None,
            {"role": "visitor", "auth_time": int(time.time())},
        )
        key = Ed25519PrivateKey.generate()
        self._enroll(self.service, buyer, "device:buyer-suspended", key)
        with self.assertRaisesRegex(ServiceError, "MERCHANT_ACCOUNT_INACTIVE"):
            self.service.preview_coupon(buyer, PreviewCouponRequest(qr_payload=issued.qr_payload))
        with self.assertRaisesRegex(ServiceError, "MERCHANT_ACCOUNT_INACTIVE"):
            self.service.begin_redemption(
                buyer,
                BeginRedemptionRequest(qr_payload=issued.qr_payload, device_key_id="device:buyer-suspended"),
            )

    def test_expired_offer_cannot_be_reactivated(self) -> None:
        issued = self._issue(self._product().product_id)
        current = self.store.offers[issued.offer_id]
        self.store.offers[issued.offer_id] = replace(current, expires_at=1)
        with self.assertRaisesRegex(ServiceError, "OFFER_EXPIRED"):
            self.service.update_offer_status(
                self.merchant,
                issued.offer_id,
                OfferStatusRequest(status="ACTIVE"),
            )
        self.assertEqual(self.store.offers[issued.offer_id].status, "EXPIRED")
        self.assertEqual(self.store.tokens[current.token_ref].status, "EXPIRED")

    def test_merchant_cannot_redeem_own_offer(self) -> None:
        issued = self._issue(self._product().product_id)
        visitor_alias = Principal(
            self.merchant.uid,
            "visitor",
            None,
            {"role": "visitor", "auth_time": int(time.time())},
        )
        with self.assertRaisesRegex(ServiceError, "ROLE_CLAIM_MISMATCH"):
            self.service.begin_redemption(
                visitor_alias,
                BeginRedemptionRequest(qr_payload=issued.qr_payload, device_key_id="device:merchant-test"),
            )

    def test_rate_limit_denies_instead_of_only_raising_risk_score(self) -> None:
        self.settings.rate_high_threshold = 2
        product = self._product(stock=3)
        issued = [self._issue(product.product_id, maximum=1) for _ in range(3)]
        buyer = Principal(
            "buyer-rate",
            "visitor",
            None,
            {"role": "visitor", "auth_time": int(time.time())},
        )
        key = Ed25519PrivateKey.generate()
        device_key_id = "device:buyer-rate"
        self._enroll(self.service, buyer, device_key_id, key)
        results = []
        for item in issued:
            begin = self.service.begin_redemption(
                buyer,
                BeginRedemptionRequest(qr_payload=item.qr_payload, device_key_id=device_key_id),
            )
            message = base64.urlsafe_b64decode(
                begin.proof_message_b64u + "=" * (-len(begin.proof_message_b64u) % 4)
            )
            results.append(
                self.service.authorize_redemption(
                    buyer,
                    AuthorizeRedemptionRequest(
                        operation_id=begin.operation_id,
                        session_id=begin.session_id,
                        challenge_id=begin.challenge.challenge_id,
                        device_key_id=device_key_id,
                        device_proof_b64u=b64u(key.sign(message)),
                    ),
                )
            )
        self.assertEqual([item.decision for item in results], ["ALLOW", "ALLOW", "DENY"])
        self.assertIn("RATE_LIMIT_EXCEEDED", results[-1].reason_codes)

    def test_expired_offer_is_rejected_before_challenge(self) -> None:
        issued = self._issue(self._product().product_id)
        current = self.store.offers[issued.offer_id]
        self.store.offers[issued.offer_id] = replace(current, expires_at=1)
        buyer = Principal(
            "buyer-expired",
            "visitor",
            None,
            {"role": "visitor", "auth_time": int(time.time())},
        )
        buyer_key = Ed25519PrivateKey.generate()
        self._enroll(self.service, buyer, "device:buyer-expired", buyer_key)
        with self.assertRaisesRegex(ServiceError, "OFFER_EXPIRED"):
            self.service.begin_redemption(
                buyer,
                BeginRedemptionRequest(qr_payload=issued.qr_payload, device_key_id="device:buyer-expired"),
            )

    def test_redis_failure_fails_closed(self) -> None:
        issued = self._issue(self._product().product_id)
        failing_service = self._service(FailingReplayState())
        principal, request = self._prepare_authorization(1, issued.qr_payload)
        with self.assertRaisesRegex(ServiceError, "REPLAY_STORE_UNAVAILABLE") as raised:
            failing_service.authorize_redemption(principal, request)
        self.assertEqual(raised.exception.status_code, 503)

    def test_challenge_store_failure_is_a_stable_503_before_commit(self) -> None:
        issued = self._issue(self._product().product_id)
        failing_service = self._service(FailingChallengeReadState())
        principal, request = self._prepare_authorization(201, issued.qr_payload, failing_service)
        with self.assertRaisesRegex(ServiceError, "CHALLENGE_STORE_UNAVAILABLE") as raised:
            failing_service.authorize_redemption(principal, request)
        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(self.store.operations[request.operation_id].status, "PENDING")

    def test_rate_store_failure_is_committed_as_fail_closed_denial(self) -> None:
        issued = self._issue(self._product().product_id)
        failing_service = self._service(FailingRateState())
        principal, request = self._prepare_authorization(202, issued.qr_payload, failing_service)
        result = failing_service.authorize_redemption(principal, request)
        self.assertEqual(result.decision, "DENY")
        self.assertIn("RATE_STORE_UNAVAILABLE", result.reason_codes)
        self.assertEqual(self.store.operations[request.operation_id].status, "DENIED")

    def test_replay_cache_commit_failure_does_not_hide_postgres_commit(self) -> None:
        issued = self._issue(self._product().product_id)
        failing_service = self._service(FailingCommitState())
        principal, request = self._prepare_authorization(203, issued.qr_payload, failing_service)
        result = failing_service.authorize_redemption(principal, request)
        self.assertEqual(result.decision, "ALLOW")
        self.assertIn("REPLAY_CACHE_COMMIT_DEGRADED", result.reason_codes)
        self.assertEqual(self.store.operations[request.operation_id].status, "COMPLETED")
        repeated = failing_service.authorize_redemption(principal, request)
        self.assertTrue(repeated.idempotent)
        self.assertEqual(repeated.decision, "ALLOW")

    def test_one_stock_unit_allows_exactly_one_of_one_hundred_buyers(self) -> None:
        product = self._product(stock=1)
        issued = self._issue(product.product_id, maximum=1)
        attempts = [self._prepare_authorization(index, issued.qr_payload) for index in range(100)]
        with ThreadPoolExecutor(max_workers=32) as executor:
            results = list(executor.map(lambda item: self.service.authorize_redemption(*item), attempts))
        allowed = [result for result in results if result.decision == "ALLOW"]
        denied = [result for result in results if result.decision == "DENY"]
        self.assertEqual(len(allowed), 1)
        self.assertEqual(len(denied), 99)
        self.assertEqual(self.store.products[product.product_id].stock_quantity, 0)
        self.assertEqual(self.store.offers[issued.offer_id].redeemed_count, 1)
        self.assertEqual(self.store.offers[issued.offer_id].status, "EXHAUSTED")
        denied_index = next(index for index, result in enumerate(results) if result.decision == "DENY")
        repeated = self.service.authorize_redemption(*attempts[denied_index])
        self.assertTrue(repeated.idempotent)
        self.assertEqual(repeated.reason_codes, results[denied_index].reason_codes)
        self.assertEqual(self.store.operations[repeated.operation_id].status, "DENIED")


if __name__ == "__main__":
    unittest.main()
