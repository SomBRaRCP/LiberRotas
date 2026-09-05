from __future__ import annotations

import base64
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from trq_bec.contracts import Intent
from trq_bec.crypto import DevelopmentCryptoProvider, LAB_SUITE_ID, SuiteRegistry
from trq_bec.policy import Policy, PolicyEngine
from trq_bec.protocol import EnvelopeService
from trq_bec.risk import ContextRiskEngine
from trq_bec.server.app import create_app
from trq_bec.server.config import ServerSettings
from trq_bec.server.memory_store import MemoryDurableStore
from trq_bec.server.models import Principal
from trq_bec.server.provider import UnavailablePQCProvider
from trq_bec.server.redis_state import MemoryDistributedState
from trq_bec.server.service import CouponSecurityService


def b64u(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


class StaticAuthenticator:
    def verify(self, bearer_token: str) -> Principal:
        identities = {
            "entre-token": ("entre-uid", "entrepreneur", {"role": "entrepreneur"}),
            "visit-token": ("visit-uid", "visitor", {"role": "visitor"}),
            "admin-token": ("admin-uid", "admin", {"role": "admin", "admin": True}),
        }
        uid, role, claims = identities[bearer_token]
        return Principal(uid, role, f"{uid}@example.test", claims)


class ServerApiTests(unittest.TestCase):
    def setUp(self) -> None:
        settings = ServerSettings(
            environment="test",
            issuer="trq-bec.test",
            audience="app-liberrotas",
            policy_version="test-policy-1",
            lab_suite_enabled=True,
            token_ttl_seconds=90,
        )
        crypto = DevelopmentCryptoProvider()
        crypto.generate_signing_key(settings.issuer_key_id, "token-signing")
        crypto.generate_signing_key(settings.checkpoint_key_id, "checkpoint-signing")
        store = MemoryDurableStore(crypto)
        distributed = MemoryDistributedState()
        pqc = UnavailablePQCProvider()
        service = CouponSecurityService(
            settings=settings,
            store=store,
            distributed=distributed,
            signing_provider=crypto,
            pqc_provider=pqc,
            envelopes=EnvelopeService(crypto, SuiteRegistry({LAB_SUITE_ID}), max_ttl_seconds=300),
            risk=ContextRiskEngine({"firebase-backend"}),
            policy=PolicyEngine(Policy("test-policy-1", 7_000, 3_500, 7_000)),
        )
        app = create_app(settings, service_override=service, authenticator_override=StaticAuthenticator())
        self.client_context = TestClient(app)
        self.client = self.client_context.__enter__()
        self.store = store
        self.entre_key = Ed25519PrivateKey.generate()
        self.visit_key = Ed25519PrivateKey.generate()

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)

    def headers(self, token: str) -> dict[str, str]:
        return {"authorization": f"Bearer {token}"}

    def enroll(self, token: str, key_id: str, private: Ed25519PrivateKey):
        public = private.public_key().public_bytes_raw()
        return self.client.post(
            "/v1/trq-bec/devices/enroll",
            headers=self.headers(token),
            json={
                "device_key_id": key_id,
                "public_key_b64u": b64u(public),
                "algorithm": "ED25519_LAB",
                "storage_profile": "EXPO_SECURE_STORE_LAB",
            },
        )

    def full_flow(self):
        self.assertEqual(self.enroll("entre-token", "device:entre-test", self.entre_key).status_code, 200)
        self.assertEqual(self.enroll("visit-token", "device:visit-test", self.visit_key).status_code, 200)
        issued = self.client.post(
            "/v1/trq-bec/coupons/issue",
            headers=self.headers("entre-token"),
            json={
                "coupon_id": "FEITUR-001",
                "issuer_id": "entre-uid",
                "city": "Pinhais - PR",
                "device_key_id": "device:entre-test",
            },
        )
        self.assertEqual(issued.status_code, 200, issued.text)
        qr = issued.json()["qr_payload"]
        begun = self.client.post(
            "/v1/trq-bec/coupons/redeem/begin",
            headers=self.headers("visit-token"),
            json={"qr_payload": qr, "device_key_id": "device:visit-test"},
        )
        self.assertEqual(begun.status_code, 200, begun.text)
        begin = begun.json()
        proof_message = base64.urlsafe_b64decode(begin["proof_message_b64u"] + "=" * (-len(begin["proof_message_b64u"]) % 4))
        signature = b64u(self.visit_key.sign(proof_message))
        request = {
            "operation_id": begin["operation_id"],
            "session_id": begin["session_id"],
            "challenge_id": begin["challenge"]["challenge_id"],
            "device_key_id": "device:visit-test",
            "device_proof_b64u": signature,
        }
        authorized = self.client.post(
            "/v1/trq-bec/coupons/redeem/authorize",
            headers=self.headers("visit-token"),
            json=request,
        )
        return qr, request, authorized

    def test_issue_and_redeem_coupon(self) -> None:
        qr, request, authorized = self.full_flow()
        self.assertEqual(authorized.status_code, 200, authorized.text)
        result = authorized.json()
        self.assertEqual(result["decision"], "ALLOW")
        self.assertTrue(result["crypto_ok"])
        self.assertEqual(result["coupon_id"], "FEITUR-001")
        self.assertTrue(result["event_ref"].startswith("event:"))
        second = self.client.post(
            "/v1/trq-bec/coupons/redeem/authorize",
            headers=self.headers("visit-token"),
            json=request,
        )
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json()["idempotent"])
        replay_begin = self.client.post(
            "/v1/trq-bec/coupons/redeem/begin",
            headers=self.headers("visit-token"),
            json={"qr_payload": qr, "device_key_id": "device:visit-test"},
        )
        self.assertEqual(replay_begin.status_code, 409)

    def test_visitor_cannot_issue_coupon(self) -> None:
        self.assertEqual(self.enroll("visit-token", "device:visit-test", self.visit_key).status_code, 200)
        response = self.client.post(
            "/v1/trq-bec/coupons/issue",
            headers=self.headers("visit-token"),
            json={
                "coupon_id": "FEITUR-001",
                "issuer_id": "visit-uid",
                "city": "Pinhais - PR",
                "device_key_id": "device:visit-test",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "ENTREPRENEUR_CLAIM_REQUIRED")

    def test_device_key_cannot_be_rebound(self) -> None:
        first = self.enroll("visit-token", "device:shared-test", self.visit_key)
        second = self.enroll("entre-token", "device:shared-test", self.entre_key)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)

    def test_wrong_device_proof_is_denied(self) -> None:
        self.assertEqual(self.enroll("entre-token", "device:entre-test", self.entre_key).status_code, 200)
        self.assertEqual(self.enroll("visit-token", "device:visit-test", self.visit_key).status_code, 200)
        issued = self.client.post(
            "/v1/trq-bec/coupons/issue",
            headers=self.headers("entre-token"),
            json={
                "coupon_id": "FEITUR-002",
                "issuer_id": "entre-uid",
                "city": "Pinhais - PR",
                "device_key_id": "device:entre-test",
            },
        )
        begun = self.client.post(
            "/v1/trq-bec/coupons/redeem/begin",
            headers=self.headers("visit-token"),
            json={"qr_payload": issued.json()["qr_payload"], "device_key_id": "device:visit-test"},
        ).json()
        wrong_key = Ed25519PrivateKey.generate()
        proof_message = base64.urlsafe_b64decode(
            begun["proof_message_b64u"] + "=" * (-len(begun["proof_message_b64u"]) % 4)
        )
        denied = self.client.post(
            "/v1/trq-bec/coupons/redeem/authorize",
            headers=self.headers("visit-token"),
            json={
                "operation_id": begun["operation_id"],
                "session_id": begun["session_id"],
                "challenge_id": begun["challenge"]["challenge_id"],
                "device_key_id": "device:visit-test",
                "device_proof_b64u": b64u(wrong_key.sign(proof_message)),
            },
        )
        self.assertEqual(denied.status_code, 200)
        self.assertEqual(denied.json()["decision"], "DENY")
        self.assertIn("DEVICE_PROOF_INVALID", denied.json()["reason_codes"])

    def test_health_reports_pq_blocked(self) -> None:
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["database"])
        self.assertFalse(response.json()["pqc_ready"])

    def test_openapi_contract_is_grouped_secured_and_public_only(self) -> None:
        schema = self.client.get("/openapi.json").json()
        self.assertEqual(
            [tag["name"] for tag in schema["tags"]],
            ["Saúde e prontidão", "Dispositivos", "Cupons", "Resgate"],
        )
        self.assertNotIn("/internal/v1/ledger/checkpoint", schema["paths"])
        security_scheme = schema["components"]["securitySchemes"]["FirebaseIDToken"]
        self.assertEqual(security_scheme["type"], "http")
        self.assertEqual(security_scheme["scheme"], "bearer")
        issue = schema["paths"]["/v1/trq-bec/coupons/issue"]["post"]
        self.assertEqual(issue["security"], [{"FirebaseIDToken": []}])
        self.assertIn("503", issue["responses"])
        self.assertNotIn("security", schema["paths"]["/health/"]["get"])


    def test_internal_openapi_is_isolated_from_public_contract(self) -> None:
        schema = self.client.get("/internal/openapi.json").json()
        self.assertEqual([tag["name"] for tag in schema["tags"]], ["Operações internas"])
        self.assertEqual(set(schema["paths"]), {"/internal/v1/ledger/checkpoint"})
        checkpoint = schema["paths"]["/internal/v1/ledger/checkpoint"]["post"]
        self.assertEqual(checkpoint["security"], [{"FirebaseIDToken": []}])
        forbidden_examples = checkpoint["responses"]["403"]["content"]["application/json"]["examples"]
        self.assertEqual(
            forbidden_examples["claimAdmin"]["value"]["code"],
            "ADMIN_CLAIM_REQUIRED",
        )

    def test_error_examples_match_each_route(self) -> None:
        schema = self.client.get("/openapi.json").json()
        begin = schema["paths"]["/v1/trq-bec/coupons/redeem/begin"]["post"]
        bad_request_examples = begin["responses"]["400"]["content"]["application/json"]["examples"]
        self.assertEqual(
            {example["value"]["code"] for example in bad_request_examples.values()},
            {"QR_BINDING_MISMATCH", "TOKEN_CRYPTO_INVALID"},
        )
        issue = schema["paths"]["/v1/trq-bec/coupons/issue"]["post"]
        not_found_examples = issue["responses"]["404"]["content"]["application/json"]["examples"]
        self.assertEqual(
            not_found_examples["cupomIndisponivel"]["value"]["code"],
            "COUPON_NOT_ACTIVE_OR_NOT_OWNED",
        )
        authorize = schema["paths"]["/v1/trq-bec/coupons/redeem/authorize"]["post"]
        unavailable_examples = authorize["responses"]["503"]["content"]["application/json"]["examples"]
        self.assertEqual(
            unavailable_examples["replayIndisponivel"]["value"]["code"],
            "REPLAY_STORE_UNAVAILABLE",
        )

    def test_empty_ledger_checkpoint_matches_documented_conflict(self) -> None:
        response = self.client.post(
            "/internal/v1/ledger/checkpoint",
            headers=self.headers("admin-token"),
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"code": "LEDGER_EMPTY", "message": "LEDGER_EMPTY"})

    def test_public_schema_descriptions_are_in_portuguese(self) -> None:
        schema = self.client.get("/openapi.json").json()
        api_error = schema["components"]["schemas"]["ApiErrorResponse"]
        self.assertIn("Código de motivo", api_error["properties"]["code"]["description"])
        enroll = schema["components"]["schemas"]["EnrollDeviceRequest"]
        self.assertIn("Identificador estável", enroll["properties"]["device_key_id"]["description"])

    def test_missing_bearer_has_stable_error_contract(self) -> None:
        response = self.client.post(
            "/v1/trq-bec/devices/enroll",
            json={
                "device_key_id": "device:visit-test",
                "public_key_b64u": b64u(self.visit_key.public_key().public_bytes_raw()),
                "algorithm": "ED25519_LAB",
                "storage_profile": "EXPO_SECURE_STORE_LAB",
            },
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json(),
            {"code": "AUTH_BEARER_REQUIRED", "message": "AUTH_BEARER_REQUIRED"},
        )
        self.assertEqual(response.headers["www-authenticate"], "Bearer")

    def test_crypto_health_has_typed_object_contract(self) -> None:
        response = self.client.get("/health/crypto")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.json()),
            {"provider", "version", "approved", "self_test_passed", "ml_kem_768", "ml_dsa_65", "ready"},
        )


if __name__ == "__main__":
    unittest.main()
