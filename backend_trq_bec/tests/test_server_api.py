from __future__ import annotations

import base64
import hashlib
import time
import unittest
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from trq_bec.contracts import Intent
from trq_bec.crypto import DevelopmentCryptoProvider, LAB_SUITE_ID, SuiteRegistry
from trq_bec.policy import Policy, PolicyEngine
from trq_bec.protocol import EnvelopeService
from trq_bec.risk import ContextRiskEngine
from trq_bec.server.access_control import default_permissions
from trq_bec.server.app import create_app
from trq_bec.server.config import ServerSettings
from trq_bec.server.email_verification import PublicIdentity
from trq_bec.server.institution_provisioning import ProvisionedInstitutionIdentity
from trq_bec.server.media_storage import (
    DisabledStorageProvider,
    MediaObjectNotFound,
    MediaStorageError,
    StorageObjectMetadata,
)
from trq_bec.server.memory_store import MemoryDurableStore
from trq_bec.server.models import (
    AccessAccountRecord,
    InstitutionProfileRecord,
    MerchantRecord,
    Principal,
    PrivilegedAccountValidationRecord,
)
from trq_bec.server.provider import UnavailablePQCProvider
from trq_bec.server.redis_state import MemoryDistributedState
from trq_bec.server.service import CouponSecurityService
from trq_bec.server.staff_provisioning import (
    ProvisionedStaffIdentity,
    StaffIdentityState,
)


@dataclass(frozen=True, slots=True)
class ProcessedImage:
    data: bytes
    content_type: str
    width: int
    height: int
    checksum_sha256: str
    variants: tuple["ProcessedImageVariant", ...] = ()


@dataclass(frozen=True, slots=True)
class ProcessedImageVariant:
    variant: str
    data: bytes
    content_type: str
    width: int
    height: int
    checksum_sha256: str


def b64u(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def nested_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(nested_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(nested_keys(item) for item in value))
    return set()


class StaticAuthenticator:
    def verify(self, bearer_token: str) -> Principal:
        identities = {
            "entre-token": ("entre-uid", "entrepreneur", {"role": "entrepreneur"}),
            "entre-other-token": (
                "entre-other-uid",
                "entrepreneur",
                {"role": "entrepreneur"},
            ),
            "visit-token": ("visit-uid", "visitor", {"role": "visitor"}),
            "admin-token": ("admin-uid", "admin", {"role": "admin", "admin": True}),
            "support-token": ("support-uid", "support", {"role": "support"}),
            "security-token": ("security-uid", "security", {"role": "security"}),
            "institution-token": ("institution-uid", "institution", {"role": "institution"}),
            "institution-other-token": (
                "institution-other-uid",
                "institution",
                {"role": "institution"},
            ),
            "missing-role-token": ("missing-role-uid", None, {}),
            "unknown-role-token": ("unknown-role-uid", "owner", {"role": "owner"}),
            "mismatch-token": ("mismatch-uid", "support", {"role": "support"}),
            "suspended-token": ("suspended-uid", "support", {"role": "support"}),
            "no-panel-permission-token": ("no-panel-uid", "security", {"role": "security"}),
            "admin-string-token": ("admin-string-uid", "admin", {"role": "admin", "admin": "false"}),
            "fallback-token": ("fallback-uid", None, {}),
            "unknown-fallback-token": ("unknown-fallback-uid", "owner", {"role": "owner"}),
            "new-public-token": (
                "new-public-uid",
                None,
                {"email_verified": False},
            ),
            "new-public-role-token": (
                "new-public-uid",
                "visitor",
                {"role": "visitor", "email_verified": False},
            ),
            "new-public-verified-token": (
                "new-public-uid",
                "visitor",
                {"role": "visitor", "email_verified": True},
            ),
            "new-entre-public-token": (
                "new-entre-public-uid",
                None,
                {"email_verified": False},
            ),
            "new-entre-public-role-token": (
                "new-entre-public-uid",
                "entrepreneur",
                {"role": "entrepreneur", "email_verified": False},
            ),
            "stale-token": ("stale-uid", "visitor", {"role": "visitor"}),
            "stale-visit-token": ("visit-uid", "visitor", {"role": "visitor"}),
            "stale-entre-token": (
                "entre-uid",
                "entrepreneur",
                {"role": "entrepreneur"},
            ),
            "stale-admin-token": ("admin-uid", "admin", {"role": "admin", "admin": True}),
            "stale-support-token": ("support-uid", "support", {"role": "support"}),
            "stale-security-token": ("security-uid", "security", {"role": "security"}),
            "new-staff-pending-token": (
                "new-staff-1",
                "support",
                {
                    "role": "support",
                    "staff_validated": False,
                    "email_verified": True,
                },
            ),
            "new-staff-validated-token": (
                "new-staff-1",
                "support",
                {
                    "role": "support",
                    "staff_validated": True,
                    "email_verified": True,
                },
            ),
            "unvalidated-support-token": (
                "unvalidated-support-uid",
                "support",
                {"role": "support", "staff_validated": True},
            ),
        }
        uid, role, claims = identities[bearer_token]
        auth_time = (
            int(time.time()) - 7_200
            if bearer_token
            in {
                "stale-token",
                "stale-visit-token",
                "stale-entre-token",
                "stale-admin-token",
                "stale-support-token",
                "stale-security-token",
            }
            else int(time.time())
        )
        return Principal(uid, role, f"{uid}@example.test", {**claims, "auth_time": auth_time})


class MemoryCommunityPublisher:
    def __init__(self) -> None:
        self.profiles: dict[str, object] = {}
        self.posts: dict[str, dict[str, object]] = {}
        self.places: dict[str, dict[str, object]] = {}
        self.fairs: dict[str, dict[str, object]] = {}

    def upsert_public_profile(self, profile):
        self.profiles[profile.firebase_uid] = profile

    def create_post(
        self,
        uid,
        email,
        role,
        request,
        created_at_ms,
        document_id=None,
    ):
        document_id = document_id or f"post-{len(self.posts) + 1}"
        self.posts[document_id] = {
            "uid": uid,
            "email": email,
            "role": role,
            "request": request,
            "created_at_ms": created_at_ms,
        }
        return document_id

    def update_post(self, uid, post_id, request, updated_at_ms):
        post = self.posts.get(post_id)
        if post is None:
            from trq_bec.server.community import CommunityDocumentNotFound

            raise CommunityDocumentNotFound("COMMUNITY_POST_NOT_FOUND")
        if post["uid"] != uid:
            from trq_bec.server.community import CommunityDocumentForbidden

            raise CommunityDocumentForbidden("COMMUNITY_POST_FORBIDDEN")
        post["request"] = request
        post["updated_at_ms"] = updated_at_ms

    def delete_post(self, uid, post_id):
        post = self.posts.get(post_id)
        if post is None:
            from trq_bec.server.community import CommunityDocumentNotFound

            raise CommunityDocumentNotFound("COMMUNITY_POST_NOT_FOUND")
        if post["uid"] != uid:
            from trq_bec.server.community import CommunityDocumentForbidden

            raise CommunityDocumentForbidden("COMMUNITY_POST_FORBIDDEN")
        del self.posts[post_id]

    def create_place(self, uid, email, request, created_at_ms):
        from trq_bec.server.community import CommunityDocumentConflict

        if any(place["uid"] == uid for place in self.places.values()):
            raise CommunityDocumentConflict("CURATED_PLACE_ALREADY_EXISTS")
        document_id = f"place-{len(self.places) + 1}"
        self.places[document_id] = {
            "uid": uid,
            "email": email,
            "request": request,
            "created_at_ms": created_at_ms,
        }
        return document_id

    def delete_place(self, uid, place_id):
        from trq_bec.server.community import (
            CommunityDocumentForbidden,
            CommunityDocumentNotFound,
        )

        place = self.places.get(place_id)
        if place is None:
            raise CommunityDocumentNotFound("CURATED_PLACE_NOT_FOUND")
        if place["uid"] != uid:
            raise CommunityDocumentForbidden("CURATED_PLACE_NOT_OWNED")
        del self.places[place_id]

    def create_live_fair(self, uid, email, request, created_at_ms, status):
        document_id = f"fair-{len(self.fairs) + 1}"
        self.fairs[document_id] = {
            "uid": uid,
            "email": email,
            "request": request,
            "created_at_ms": created_at_ms,
            "status": status,
        }
        return document_id

    def end_live_fair(self, uid, fair_id, ended_at_ms):
        from trq_bec.server.community import (
            CommunityDocumentForbidden,
            CommunityDocumentNotFound,
        )

        fair = self.fairs.get(fair_id)
        if fair is None:
            raise CommunityDocumentNotFound("LIVE_FAIR_NOT_FOUND")
        if fair["uid"] != uid:
            raise CommunityDocumentForbidden("LIVE_FAIR_NOT_OWNED")
        fair["status"] = "ended"
        fair["ended_at_ms"] = ended_at_ms

    def delete_live_fair(self, uid, fair_id):
        from trq_bec.server.community import (
            CommunityDocumentForbidden,
            CommunityDocumentNotFound,
        )

        fair = self.fairs.get(fair_id)
        if fair is None:
            raise CommunityDocumentNotFound("LIVE_FAIR_NOT_FOUND")
        if fair["uid"] != uid:
            raise CommunityDocumentForbidden("LIVE_FAIR_NOT_OWNED")
        del self.fairs[fair_id]

    def owns_live_fair(self, uid, fair_id):
        fair = self.fairs.get(fair_id)
        return fair is not None and fair["uid"] == uid


class FakeStorageProvider:
    """Simula somente o contrato privado usado pelo servico de midia."""

    name = "gcs"
    enabled = True
    configured = True

    def __init__(self, bucket_name: str) -> None:
        self.bucket_name = bucket_name
        self.objects: dict[str, dict[str, object]] = {}
        self.deleted: list[str] = []
        self.replace_calls = 0
        self.create_upload_error_code: str | None = None
        self.metadata_error_code: str | None = None
        self.delete_error_code: str | None = None

    def create_upload_url(
        self,
        object_key: str,
        content_type: str,
        media_id: str,
        expires_in: int,
    ) -> tuple[str, dict[str, str]]:
        if self.create_upload_error_code is not None:
            raise MediaStorageError(self.create_upload_error_code)
        return (
            f"https://storage.example.test/upload/{media_id}?signed=test",
            {
                "Content-Type": content_type,
                "x-goog-meta-media-id": media_id,
            },
        )

    def simulate_signed_put(
        self,
        authorization: dict[str, object],
        data: bytes,
    ) -> None:
        required_headers = authorization["required_headers"]
        assert isinstance(required_headers, dict)
        object_key = authorization["object_key"]
        assert isinstance(object_key, str)
        content_type = required_headers["Content-Type"]
        media_id = required_headers["x-goog-meta-media-id"]
        self.objects[object_key] = {
            "data": data,
            "content_type": content_type,
            "metadata": {"media-id": media_id},
            "crc32c": "AAAAAA==",
            "generation": 1,
        }

    def create_download_url(self, object_key: str, expires_in: int) -> str:
        if object_key not in self.objects:
            raise MediaObjectNotFound()
        return f"https://storage.example.test/download/{object_key}?signed={expires_in}"

    def get_metadata(self, object_key: str) -> StorageObjectMetadata:
        if self.metadata_error_code is not None:
            raise MediaStorageError(self.metadata_error_code)
        stored = self.objects.get(object_key)
        if stored is None:
            raise MediaObjectNotFound()
        data = stored["data"]
        assert isinstance(data, bytes)
        metadata = stored["metadata"]
        assert isinstance(metadata, dict)
        return StorageObjectMetadata(
            bucket_name=self.bucket_name,
            object_key=object_key,
            size_bytes=len(data),
            content_type=str(stored["content_type"]),
            crc32c=str(stored["crc32c"]),
            generation=int(stored["generation"]),
            metadata={str(key): str(value) for key, value in metadata.items()},
        )

    def download_bytes(self, object_key: str, generation: int | None) -> bytes:
        metadata = self.get_metadata(object_key)
        assert generation == metadata.generation
        data = self.objects[object_key]["data"]
        assert isinstance(data, bytes)
        return data

    def replace_object(
        self,
        object_key: str,
        data: bytes,
        content_type: str,
        media_id: str,
        generation: int | None,
    ) -> StorageObjectMetadata:
        self.replace_calls += 1
        current = self.get_metadata(object_key)
        assert generation == current.generation
        self.objects[object_key] = {
            "data": data,
            "content_type": content_type,
            "metadata": {"media-id": media_id, "processed": "true"},
            "crc32c": "BBBBBB==",
            "generation": (generation or 0) + 1,
        }
        return self.get_metadata(object_key)

    def put_derived_object(
        self,
        object_key: str,
        data: bytes,
        content_type: str,
        media_id: str,
        variant: str,
        checksum_sha256: str,
    ) -> StorageObjectMetadata:
        expected_metadata = {
            "media-id": media_id,
            "variant": variant,
            "checksum-sha256": checksum_sha256,
            "processed": "true",
        }
        existing = self.objects.get(object_key)
        if existing is not None:
            if (
                existing["data"] != data
                or existing["content_type"] != content_type
                or existing["metadata"] != expected_metadata
            ):
                raise MediaStorageError("MEDIA_OBJECT_CONFLICT")
            return self.get_metadata(object_key)
        self.objects[object_key] = {
            "data": data,
            "content_type": content_type,
            "metadata": expected_metadata,
            "crc32c": "CCCCCC==",
            "generation": 1,
        }
        return self.get_metadata(object_key)

    def delete_object(self, object_key: str, generation: int | None) -> None:
        if self.delete_error_code is not None:
            raise MediaStorageError(self.delete_error_code)
        self.deleted.append(object_key)
        self.objects.pop(object_key, None)


class MemoryInstitutionProvisioner:
    def __init__(self) -> None:
        self.created: dict[str, dict[str, object]] = {}
        self.rolled_back: list[str] = []
        self.next_id = 1

    def provision(self, email: str, name: str) -> ProvisionedInstitutionIdentity:
        firebase_uid = f"new-institution-{self.next_id}"
        self.next_id += 1
        self.created[firebase_uid] = {
            "email": email,
            "name": name,
            "claims": {"role": "institution", "admin": False},
        }
        return ProvisionedInstitutionIdentity(firebase_uid, email)

    def rollback(self, firebase_uid: str) -> None:
        self.rolled_back.append(firebase_uid)
        self.created.pop(firebase_uid, None)


class MemoryStaffProvisioner:
    def __init__(self) -> None:
        self.created: dict[str, dict[str, object]] = {}
        self.rolled_back: list[str] = []
        self.next_id = 1

    def provision(
        self,
        email: str,
        display_name: str,
        role: str,
    ) -> ProvisionedStaffIdentity:
        firebase_uid = f"new-staff-{self.next_id}"
        self.next_id += 1
        self.created[firebase_uid] = {
            "email": email,
            "display_name": display_name,
            "role": role,
            "email_verified": False,
            "validated": False,
        }
        return ProvisionedStaffIdentity(firebase_uid, email, role)

    def inspect(self, firebase_uid: str) -> StaffIdentityState:
        identity = self.created[firebase_uid]
        return StaffIdentityState(
            firebase_uid=firebase_uid,
            email=str(identity["email"]),
            role=str(identity["role"]),
            email_verified=bool(identity["email_verified"]),
            disabled=False,
        )

    def set_validated(
        self,
        firebase_uid: str,
        role: str,
        validated: bool,
    ) -> None:
        identity = self.created[firebase_uid]
        assert identity["role"] == role
        identity["validated"] = validated

    def rollback(self, firebase_uid: str) -> None:
        self.rolled_back.append(firebase_uid)
        self.created.pop(firebase_uid, None)


class MemoryDeviceSecurityNotifier:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object, str, int]] = []
        self.status = "SENT"
        self.fail = False

    def send_new_device_approval(self, uid, device, approval_token, ttl_seconds):
        self.calls.append((uid, device, approval_token, ttl_seconds))
        if self.fail:
            raise ConnectionError("smtp unavailable")
        return self.status


class MemoryAccountSessionRevoker:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail = False

    def revoke_all(self, uid: str) -> None:
        self.calls.append(uid)
        if self.fail:
            raise ConnectionError("firebase unavailable")


class MemoryPublicIdentityProvisioner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def provision(self, uid: str, role: str) -> PublicIdentity:
        self.calls.append((uid, role))
        return PublicIdentity(
            firebase_uid=uid,
            email=f"{uid}@example.test",
            email_verified=False,
            role=role,
        )


class MemoryEmailVerificationSender:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.result = "SENT"

    def send(self, uid: str, expected_email: str) -> str:
        self.calls.append((uid, expected_email))
        return self.result

    def send_password_setup(self, uid: str, expected_email: str) -> str:
        self.calls.append((uid, expected_email))
        return self.result


class ServerApiTests(unittest.TestCase):
    def setUp(self) -> None:
        settings = ServerSettings(
            environment="test",
            issuer="trq-bec.test",
            audience="app-liberrotas",
            policy_version="test-policy-1",
            lab_suite_enabled=True,
            token_ttl_seconds=90,
            gcs_bucket_name="liberrotas-test-private",
        )
        crypto = DevelopmentCryptoProvider()
        crypto.generate_signing_key(settings.issuer_key_id, "token-signing")
        crypto.generate_signing_key(settings.checkpoint_key_id, "checkpoint-signing")
        store = MemoryDurableStore(crypto)
        for uid, email, role in (
            ("entre-uid", "entre-uid@example.test", "entrepreneur"),
            (
                "entre-other-uid",
                "entre-other-uid@example.test",
                "entrepreneur",
            ),
            ("visit-uid", "visit-uid@example.test", "visitor"),
            ("admin-uid", "admin-uid@example.test", "admin"),
            ("support-uid", "support-uid@example.test", "support"),
            ("security-uid", "security-uid@example.test", "security"),
            ("institution-uid", "institution-uid@example.test", "institution"),
            (
                "institution-other-uid",
                "institution-other-uid@example.test",
                "institution",
            ),
        ):
            store.set_access_account(
                AccessAccountRecord(
                    firebase_uid=uid,
                    email=email,
                    role=role,
                    status="ACTIVE",
                    allow_entrepreneur_fallback=False,
                    permissions=default_permissions(role),
                )
            )
        validated_at = datetime.now(timezone.utc)
        for uid, role in (
            ("admin-uid", "admin"),
            ("support-uid", "support"),
            ("security-uid", "security"),
        ):
            store.set_privileged_account_validation(
                PrivilegedAccountValidationRecord(
                    firebase_uid=uid,
                    requested_role=role,
                    validation_state="APPROVED",
                    protection_level="SYSTEM",
                    account_origin="BOOTSTRAP",
                    created_by_uid="system:test-bootstrap",
                    validated_by_uid="system:test-bootstrap",
                    validation_reason=(
                        "Conta oficial validada pelo bootstrap dos testes."
                    ),
                    validated_at=validated_at,
                    created_at=validated_at,
                    updated_at=validated_at,
                )
            )
        store.merchants["entre-uid"] = MerchantRecord(
            firebase_uid="entre-uid",
            display_name="Artesã da Feira",
            establishment_id="EST-FEIRA-TESTE",
            establishment_name="Feira LiberRotas",
            status="ACTIVE",
        )
        store.merchants["entre-other-uid"] = MerchantRecord(
            firebase_uid="entre-other-uid",
            display_name="Outro Empreendedor",
            establishment_id="EST-OUTRO-TESTE",
            establishment_name="Outro Comercio",
            status="ACTIVE",
        )
        distributed = MemoryDistributedState()
        pqc = UnavailablePQCProvider()
        self.community = MemoryCommunityPublisher()
        self.institution_provisioner = MemoryInstitutionProvisioner()
        self.staff_provisioner = MemoryStaffProvisioner()
        self.device_notifier = MemoryDeviceSecurityNotifier()
        self.session_revoker = MemoryAccountSessionRevoker()
        self.public_identity_provisioner = MemoryPublicIdentityProvisioner()
        self.email_verification_sender = MemoryEmailVerificationSender()
        self.media_storage = FakeStorageProvider("liberrotas-test-private")
        service = CouponSecurityService(
            settings=settings,
            store=store,
            distributed=distributed,
            signing_provider=crypto,
            pqc_provider=pqc,
            envelopes=EnvelopeService(
                crypto,
                SuiteRegistry({LAB_SUITE_ID}),
                max_ttl_seconds=settings.live_offer_max_ttl_seconds,
            ),
            risk=ContextRiskEngine({"firebase-backend"}),
            policy=PolicyEngine(Policy("test-policy-1", 7_000, 3_500, 7_000)),
            community_publisher=self.community,
            institution_provisioner=self.institution_provisioner,
            staff_provisioner=self.staff_provisioner,
            device_security_notifier=self.device_notifier,
            account_session_revoker=self.session_revoker,
            public_identity_provisioner=self.public_identity_provisioner,
            email_verification_sender=self.email_verification_sender,
            media_storage=self.media_storage,
        )
        self.cleaned_account_uids: list[str] = []

        def cleanup_account(uid: str) -> int:
            self.cleaned_account_uids.append(uid)
            return 7

        app = create_app(
            settings,
            service_override=service,
            authenticator_override=StaticAuthenticator(),
            account_cleanup_override=cleanup_account,
        )
        self.client_context = TestClient(app)
        self.client = self.client_context.__enter__()
        self.service = service
        self.store = store
        institution_now = datetime.now(timezone.utc)
        for uid, email, name in (
            ("institution-uid", "institution-uid@example.test", "Instituicao Principal"),
            (
                "institution-other-uid",
                "institution-other-uid@example.test",
                "Instituicao Secundaria",
            ),
        ):
            self.store.institution_profiles[uid] = InstitutionProfileRecord(
                firebase_uid=uid,
                email=email,
                name=name,
                description=None,
                city="Pinhais",
                status="ACTIVE",
                created_at=institution_now,
                updated_at=institution_now,
            )
        self.entre_key = Ed25519PrivateKey.generate()
        self.visit_key = Ed25519PrivateKey.generate()

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)

    def headers(self, token: str) -> dict[str, str]:
        return {"authorization": f"Bearer {token}"}

    def seed_staff_validation(
        self,
        uid: str,
        role: str,
        *,
        protection_level: str = "PRIVILEGED",
    ) -> None:
        now = datetime.now(timezone.utc)
        self.store.set_privileged_account_validation(
            PrivilegedAccountValidationRecord(
                firebase_uid=uid,
                requested_role=role,
                validation_state="APPROVED",
                protection_level=protection_level,
                account_origin="BOOTSTRAP",
                created_by_uid="system:test-bootstrap",
                validated_by_uid="system:test-bootstrap",
                validation_reason="Conta privilegiada validada para este cenário de teste.",
                validated_at=now,
                created_at=now,
                updated_at=now,
            )
        )

    def test_visitor_registration_does_not_block_or_queue_verification_email(self) -> None:
        registered = self.client.post(
            "/v1/access/public-registration",
            headers=self.headers("new-public-token"),
            json={
                "role": "visitor",
                "display_name": "Nova Pessoa",
            },
        )
        self.assertEqual(registered.status_code, 202, registered.text)
        self.assertEqual(
            registered.json(),
            {"status": "NOT_REQUIRED", "role": "visitor"},
        )
        account = self.store.get_access_account("new-public-uid")
        self.assertIsNotNone(account)
        assert account is not None
        self.assertEqual(account.role, "visitor")
        self.assertEqual(account.status, "ACTIVE")

        authorized_before_verification = self.client.get(
            "/v1/access/me",
            headers=self.headers("new-public-role-token"),
        )
        self.assertEqual(
            authorized_before_verification.status_code,
            200,
            authorized_before_verification.text,
        )
        self.assertEqual(
            authorized_before_verification.json()["reason"],
            "ACCESS_GRANTED",
        )
        self.assertEqual(
            authorized_before_verification.json()["access_state"],
            "AUTHORIZED",
        )
        self.assertEqual(authorized_before_verification.json()["role"], "visitor")

        resend = self.client.post(
            "/v1/access/email-verification/resend",
            headers=self.headers("new-public-role-token"),
        )
        self.assertEqual(resend.status_code, 202, resend.text)
        self.assertEqual(resend.json(), {"status": "NOT_REQUIRED", "role": "visitor"})

        self.assertEqual(self.service.process_email_verification_queue(), 0)
        self.assertEqual(self.email_verification_sender.calls, [])
        queue_items = list(self.store.email_verification_queue.values())
        self.assertEqual(queue_items, [])

        authorized = self.client.get(
            "/v1/access/me",
            headers=self.headers("new-public-verified-token"),
        )
        self.assertEqual(authorized.status_code, 200, authorized.text)
        self.assertEqual(authorized.json()["access_state"], "AUTHORIZED")

    def test_unverified_entrepreneur_access_remains_pending(self) -> None:
        registered = self.client.post(
            "/v1/access/public-registration",
            headers=self.headers("new-entre-public-token"),
            json={
                "role": "entrepreneur",
                "display_name": "Novo Empreendedor",
                "establishment_name": "Ateliê Novo Empreendedor",
            },
        )
        self.assertEqual(registered.status_code, 202, registered.text)
        self.assertEqual(
            registered.json(),
            {"status": "QUEUED", "role": "entrepreneur"},
        )

        pending = self.client.get(
            "/v1/access/me",
            headers=self.headers("new-entre-public-role-token"),
        )
        self.assertEqual(pending.status_code, 200, pending.text)
        self.assertEqual(pending.json()["reason"], "EMAIL_VERIFICATION_REQUIRED")
        self.assertEqual(pending.json()["access_state"], "PENDING")

    def test_public_registration_never_accepts_privileged_role(self) -> None:
        rejected = self.client.post(
            "/v1/access/public-registration",
            headers=self.headers("new-public-token"),
            json={
                "role": "admin",
                "display_name": "Tentativa Privilegiada",
            },
        )
        self.assertEqual(rejected.status_code, 422, rejected.text)
        self.assertIsNone(self.store.get_access_account("new-public-uid"))
        self.assertEqual(self.public_identity_provisioner.calls, [])

    def save_public_profile(
        self,
        token: str,
        display_name: str,
        *,
        city: str = "Pinhais",
        category: str = "Artesanato",
        avatar_uri: str | None = None,
    ):
        return self.client.put(
            "/v1/profile/public",
            headers=self.headers(token),
            json={
                "display_name": display_name,
                "city": city,
                "address": "Rua das Flores, 100",
                "category": category,
                "interests": ["Feiras", "Turismo"],
                "avatar_uri": avatar_uri,
            },
        )

    def authorize_post_image(
        self,
        token: str,
        client_request_id: str,
        raw_image: bytes,
    ):
        return self.client.post(
            "/v1/media/uploads",
            headers=self.headers(token),
            json={
                "entity_type": "post",
                "entity_id": None,
                "media_role": "post_image",
                "original_filename": "foto-feed.jpg",
                "content_type": "image/jpeg",
                "size_bytes": len(raw_image),
                "client_request_id": client_request_id,
            },
        )

    def upload_ready_post_image(
        self,
        token: str,
        client_request_id: str,
    ) -> tuple[dict[str, object], object]:
        raw_image = b"\xff\xd8\xff-ready-image"
        authorized = self.authorize_post_image(
            token,
            client_request_id,
            raw_image,
        )
        self.assertEqual(authorized.status_code, 201, authorized.text)
        authorization = authorized.json()
        self.media_storage.simulate_signed_put(authorization, raw_image)
        processed_bytes = b"\xff\xd8\xff-ready-image-processed"
        processed = ProcessedImage(
            data=processed_bytes,
            content_type="image/jpeg",
            width=640,
            height=480,
            checksum_sha256=hashlib.sha256(processed_bytes).hexdigest(),
        )
        with patch("trq_bec.server.service.process_image", return_value=processed):
            confirmed = self.client.post(
                f"/v1/media/uploads/{authorization['media_id']}/confirm",
                headers=self.headers(token),
            )
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        return authorization, confirmed

    def enroll(
        self,
        token: str,
        key_id: str,
        private: Ed25519PrivateKey,
        storage_profile: str = "EXPO_SECURE_STORE_LAB",
        **metadata,
    ):
        public = private.public_key().public_bytes_raw()
        return self.client.post(
            "/v1/trq-bec/devices/enroll",
            headers=self.headers(token),
            json={
                "device_key_id": key_id,
                "public_key_b64u": b64u(public),
                "algorithm": "ED25519_LAB",
                "storage_profile": storage_profile,
                **metadata,
            },
        )

    def test_access_resolution_uses_claims_database_permissions_and_status(self) -> None:
        expected = {
            "admin-token": "admin",
            "support-token": "support",
            "security-token": "security",
            "institution-token": "institution",
            "entre-token": "entrepreneur",
            "visit-token": "visitor",
        }
        for token, role in expected.items():
            with self.subTest(role=role):
                response = self.client.get("/v1/access/me", headers=self.headers(token))
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["access_state"], "AUTHORIZED")
                self.assertEqual(response.json()["role"], role)
                self.assertEqual(response.json()["panel"], role)
                self.assertIn(f"{role}.panel.access", response.json()["permissions"])

        self.store.set_access_account(
            AccessAccountRecord(
                "missing-role-uid",
                "missing-role-uid@example.test",
                "entrepreneur",
                "ACTIVE",
                False,
                default_permissions("entrepreneur"),
            )
        )
        self.store.merchants["missing-role-uid"] = replace(
            self.store.merchants["entre-uid"],
            firebase_uid="missing-role-uid",
            establishment_id="EST-MISSING-ROLE",
        )
        missing_claim = self.client.get(
            "/v1/access/me", headers=self.headers("missing-role-token")
        )
        self.assertEqual(missing_claim.json()["access_state"], "PENDING")
        self.assertIsNone(missing_claim.json()["role"])
        self.assertEqual(missing_claim.json()["reason"], "CUSTOM_CLAIM_REQUIRED")

        unknown_claim = self.client.get(
            "/v1/access/me", headers=self.headers("unknown-role-token")
        )
        self.assertEqual(unknown_claim.json()["access_state"], "PENDING")
        self.assertEqual(unknown_claim.json()["reason"], "ACCESS_NOT_PROVISIONED")

        self.store.set_access_account(
            AccessAccountRecord(
                "mismatch-uid",
                "mismatch-uid@example.test",
                "security",
                "ACTIVE",
                False,
                default_permissions("security"),
            )
        )
        mismatch = self.client.get("/v1/access/me", headers=self.headers("mismatch-token"))
        self.assertEqual(mismatch.json()["access_state"], "DENIED")
        self.assertEqual(mismatch.json()["reason"], "ROLE_CLAIM_MISMATCH")

        self.store.set_access_account(
            AccessAccountRecord(
                "suspended-uid",
                "suspended-uid@example.test",
                "support",
                "SUSPENDED",
                False,
                default_permissions("support"),
            )
        )
        suspended = self.client.get("/v1/access/me", headers=self.headers("suspended-token"))
        self.assertEqual(suspended.json()["access_state"], "SUSPENDED")
        self.assertEqual(suspended.json()["panel"], "access_pending")

        self.store.set_access_account(
            AccessAccountRecord(
                "no-panel-uid",
                "no-panel-uid@example.test",
                "security",
                "ACTIVE",
                False,
                ("security.audit.read",),
            )
        )
        self.seed_staff_validation("no-panel-uid", "security")
        no_permission = self.client.get(
            "/v1/access/me", headers=self.headers("no-panel-permission-token")
        )
        self.assertEqual(no_permission.json()["access_state"], "DENIED")
        self.assertEqual(no_permission.json()["reason"], "PANEL_PERMISSION_REQUIRED")

        self.store.set_access_account(
            AccessAccountRecord(
                "admin-string-uid",
                "admin-string-uid@example.test",
                "admin",
                "ACTIVE",
                False,
                default_permissions("admin"),
            )
        )
        self.seed_staff_validation("admin-string-uid", "admin")
        false_admin = self.client.get(
            "/v1/access/me", headers=self.headers("admin-string-token")
        )
        self.assertEqual(false_admin.json()["access_state"], "DENIED")
        self.assertEqual(false_admin.json()["reason"], "ADMIN_CLAIM_REQUIRED")

        self.store.set_access_account(
            AccessAccountRecord(
                "unvalidated-support-uid",
                "unvalidated-support-uid@example.test",
                "support",
                "ACTIVE",
                False,
                default_permissions("support"),
            )
        )
        unvalidated_staff = self.client.get(
            "/v1/access/me",
            headers=self.headers("unvalidated-support-token"),
        )
        self.assertEqual(unvalidated_staff.json()["access_state"], "PENDING")
        self.assertEqual(
            unvalidated_staff.json()["reason"],
            "STAFF_AUTHORITY_VALIDATION_REQUIRED",
        )

    def test_access_resolution_rejects_role_injection_and_requires_explicit_fallback(self) -> None:
        query_attempt = self.client.get(
            "/v1/access/me?role=admin", headers=self.headers("visit-token")
        )
        body_attempt = self.client.request(
            "GET",
            "/v1/access/me",
            headers=self.headers("visit-token"),
            json={"role": "admin"},
        )
        for response in (query_attempt, body_attempt):
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["role"], "visitor")
            self.assertEqual(response.json()["panel"], "visitor")

        wrong_method = self.client.post(
            "/v1/access/me",
            headers=self.headers("visit-token"),
            json={"role": "admin"},
        )
        self.assertEqual(wrong_method.status_code, 405)

        self.store.set_access_account(
            AccessAccountRecord(
                "fallback-uid",
                "fallback-uid@example.test",
                "entrepreneur",
                "ACTIVE",
                True,
                default_permissions("entrepreneur"),
            )
        )
        self.store.merchants["fallback-uid"] = replace(
            self.store.merchants["entre-uid"],
            firebase_uid="fallback-uid",
            establishment_id="EST-EXPLICIT-FALLBACK",
        )
        fallback = self.client.get("/v1/access/me", headers=self.headers("fallback-token"))
        self.assertEqual(fallback.status_code, 200, fallback.text)
        self.assertEqual(fallback.json()["access_state"], "AUTHORIZED")
        self.assertEqual(fallback.json()["role"], "entrepreneur")

        self.store.set_access_account(
            AccessAccountRecord(
                "unknown-fallback-uid",
                "unknown-fallback-uid@example.test",
                "entrepreneur",
                "ACTIVE",
                True,
                default_permissions("entrepreneur"),
            )
        )
        self.store.merchants["unknown-fallback-uid"] = replace(
            self.store.merchants["entre-uid"],
            firebase_uid="unknown-fallback-uid",
            establishment_id="EST-UNKNOWN-FALLBACK",
        )
        unknown_fallback = self.client.get(
            "/v1/access/me", headers=self.headers("unknown-fallback-token")
        )
        self.assertEqual(unknown_fallback.status_code, 200, unknown_fallback.text)
        self.assertEqual(unknown_fallback.json()["access_state"], "PENDING")
        self.assertEqual(unknown_fallback.json()["reason"], "CUSTOM_CLAIM_UNRECOGNIZED")

        fallback_product = self.client.post(
            "/v1/marketplace/products",
            headers=self.headers("fallback-token"),
            json={
                "title": "Produto com fallback explícito",
                "description": "Autorização calculada no backend",
                "price_minor": 2500,
                "currency": "BRL",
                "stock_quantity": 2,
            },
        )
        self.assertEqual(fallback_product.status_code, 200, fallback_product.text)

    def test_server_time_is_public_utc_and_nondecreasing(self) -> None:
        first = self.client.get("/v1/time")
        second = self.client.get("/v1/time")
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        first_body = first.json()
        second_body = second.json()
        self.assertEqual(first_body["timezone"], "UTC")
        self.assertEqual(set(first_body), {"server_time_ms", "server_time_iso", "timezone"})
        parsed = datetime.fromisoformat(first_body["server_time_iso"].replace("Z", "+00:00"))
        self.assertEqual(parsed.utcoffset(), timedelta(0))
        self.assertLessEqual(
            abs(int(parsed.timestamp() * 1000) - first_body["server_time_ms"]),
            1,
        )
        self.assertGreaterEqual(second_body["server_time_ms"], first_body["server_time_ms"])

    def test_admin_provisions_and_lists_institutions_without_client_role_or_password(self) -> None:
        created = self.client.post(
            "/v1/admin/institutions",
            headers=self.headers("admin-token"),
            json={
                "email": "cultura@pinhais.example",
                "name": "Secretaria de Cultura",
                "description": "Parceira institucional",
                "city": "Pinhais",
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        body = created.json()
        self.assertEqual(body["status"], "ACTIVE")
        provisioned = self.institution_provisioner.created[body["firebase_uid"]]
        self.assertEqual(provisioned["claims"], {"role": "institution", "admin": False})

        account = self.store.get_access_account(body["firebase_uid"])
        assert account is not None
        self.assertEqual(account.role, "institution")
        self.assertEqual(account.status, "ACTIVE")
        self.assertEqual(account.permissions, tuple(sorted(default_permissions("institution"))))
        provision_event = self.store.access_audit_events[-1]
        self.assertEqual(provision_event.event_type, "INSTITUTION_PROVISIONED")
        self.assertEqual(provision_event.actor_uid, "admin-uid")
        self.assertEqual(provision_event.target_uid, body["firebase_uid"])

        listed = self.client.get(
            "/v1/admin/institutions",
            headers=self.headers("admin-token"),
        )
        self.assertEqual(listed.status_code, 200, listed.text)
        listed_ids = {item["firebase_uid"] for item in listed.json()["institutions"]}
        self.assertIn(body["firebase_uid"], listed_ids)

        injected = self.client.post(
            "/v1/admin/institutions",
            headers=self.headers("admin-token"),
            json={
                "email": "injetada@example.test",
                "name": "Conta injetada",
                "role": "admin",
                "password": "nao-deve-ser-aceita",
            },
        )
        self.assertEqual(injected.status_code, 422, injected.text)

        wrong_role = self.client.post(
            "/v1/admin/institutions",
            headers=self.headers("support-token"),
            json={"email": "bloqueada@example.test", "name": "Bloqueada"},
        )
        self.assertEqual(wrong_role.status_code, 403, wrong_role.text)
        self.assertEqual(wrong_role.json()["code"], "ADMIN_ACCESS_REQUIRED")

        stale = self.client.post(
            "/v1/admin/institutions",
            headers=self.headers("stale-admin-token"),
            json={"email": "antiga@example.test", "name": "Sessao antiga"},
        )
        self.assertEqual(stale.status_code, 403, stale.text)
        self.assertEqual(stale.json()["code"], "RECENT_AUTHENTICATION_REQUIRED")

        current_admin = self.store.get_access_account("admin-uid")
        assert current_admin is not None
        self.store.set_access_account(
            replace(
                current_admin,
                permissions=tuple(
                    permission
                    for permission in current_admin.permissions
                    if permission != "admin.institutions.manage"
                ),
            )
        )
        missing_permission = self.client.get(
            "/v1/admin/institutions",
            headers=self.headers("admin-token"),
        )
        self.assertEqual(missing_permission.status_code, 403, missing_permission.text)

    def test_institution_provisioning_rolls_back_identity_when_database_conflicts(self) -> None:
        conflict = self.client.post(
            "/v1/admin/institutions",
            headers=self.headers("admin-token"),
            json={
                "email": "institution-uid@example.test",
                "name": "E-mail ja persistido",
            },
        )
        self.assertEqual(conflict.status_code, 409, conflict.text)
        self.assertEqual(conflict.json()["code"], "INSTITUTION_ACCOUNT_EXISTS")
        self.assertEqual(self.institution_provisioner.rolled_back, ["new-institution-1"])
        self.assertNotIn("new-institution-1", self.institution_provisioner.created)
        self.assertIsNone(self.store.get_access_account("new-institution-1"))

    def test_admin_accounts_and_operations_summaries_are_authorized_and_sanitized(self) -> None:
        accounts = self.client.get(
            "/v1/admin/accounts?limit=50",
            headers=self.headers("admin-token"),
        )
        self.assertEqual(accounts.status_code, 200, accounts.text)
        account_items = accounts.json()["accounts"]
        self.assertGreater(len(account_items), 0)
        self.assertIn("permissions", account_items[0])
        self.assertNotIn("custom_claims", nested_keys(accounts.json()))
        self.assertNotIn("password", nested_keys(accounts.json()))

        operations = self.client.get(
            "/v1/admin/operations/summary",
            headers=self.headers("admin-token"),
        )
        self.assertEqual(operations.status_code, 200, operations.text)
        summary = operations.json()
        self.assertEqual(summary["accounts_total"], len(self.store.access_accounts))
        self.assertEqual(
            summary["accounts_by_role"]["institution"],
            2,
        )
        self.assertEqual(summary["institutions_total"], 2)
        self.assertTrue(summary["database_ok"])
        self.assertTrue(summary["redis_ok"])
        self.assertIn("server_time_iso", summary)
        for forbidden in {"public_key_b64u", "pix_key", "token_ref", "signature_b64u"}:
            self.assertNotIn(forbidden, nested_keys(summary))

        wrong_role = self.client.get(
            "/v1/admin/accounts",
            headers=self.headers("support-token"),
        )
        self.assertEqual(wrong_role.status_code, 403, wrong_role.text)
        self.assertEqual(wrong_role.json()["code"], "ADMIN_ACCESS_REQUIRED")

        admin = self.store.get_access_account("admin-uid")
        assert admin is not None
        self.store.set_access_account(
            replace(
                admin,
                permissions=tuple(
                    permission
                    for permission in admin.permissions
                    if permission != "admin.accounts.manage"
                ),
            )
        )
        denied_accounts = self.client.get(
            "/v1/admin/accounts",
            headers=self.headers("admin-token"),
        )
        self.assertEqual(denied_accounts.status_code, 403, denied_accounts.text)

        admin_without_accounts = self.store.get_access_account("admin-uid")
        assert admin_without_accounts is not None
        self.store.set_access_account(
            replace(
                admin_without_accounts,
                permissions=tuple(
                    permission
                    for permission in admin_without_accounts.permissions
                    if permission != "admin.marketplace.manage"
                ),
            )
        )
        denied_operations = self.client.get(
            "/v1/admin/operations/summary",
            headers=self.headers("admin-token"),
        )
        self.assertEqual(denied_operations.status_code, 403, denied_operations.text)

    def test_admin_creates_and_validates_staff_only_after_email_confirmation(self) -> None:
        created = self.client.post(
            "/v1/admin/staff-accounts",
            headers=self.headers("admin-token"),
            json={
                "email": "novo-suporte@example.test",
                "display_name": "Novo Suporte",
                "role": "support",
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        body = created.json()
        self.assertEqual(body["firebase_uid"], "new-staff-1")
        self.assertEqual(body["status"], "PENDING")
        self.assertEqual(body["role"], "support")
        self.assertEqual(body["authority_validation_state"], "PENDING")
        self.assertEqual(body["protection_level"], "PRIVILEGED")
        self.assertEqual(body["account_origin"], "ADMIN_INVITATION")
        self.assertFalse(self.staff_provisioner.created["new-staff-1"]["validated"])
        self.assertTrue(
            any(
                item.firebase_uid == "new-staff-1" and item.status == "PENDING"
                for item in self.store.email_verification_queue.values()
            )
        )

        pending_access = self.client.get(
            "/v1/access/me",
            headers=self.headers("new-staff-pending-token"),
        )
        self.assertEqual(pending_access.status_code, 200, pending_access.text)
        self.assertEqual(pending_access.json()["access_state"], "PENDING")
        self.assertEqual(
            pending_access.json()["reason"],
            "STAFF_AUTHORITY_VALIDATION_REQUIRED",
        )

        before_email = self.client.post(
            "/v1/admin/staff-accounts/new-staff-1/validate",
            headers=self.headers("admin-token"),
            json={
                "reason": (
                    "Identidade e responsabilidade funcional revisadas pelo "
                    "administrador."
                )
            },
        )
        self.assertEqual(before_email.status_code, 409, before_email.text)
        self.assertEqual(
            before_email.json()["code"],
            "STAFF_EMAIL_VERIFICATION_REQUIRED",
        )

        self.staff_provisioner.created["new-staff-1"]["email_verified"] = True
        validated = self.client.post(
            "/v1/admin/staff-accounts/new-staff-1/validate",
            headers=self.headers("admin-token"),
            json={
                "reason": (
                    "Identidade e responsabilidade funcional revisadas pelo "
                    "administrador."
                )
            },
        )
        self.assertEqual(validated.status_code, 200, validated.text)
        self.assertEqual(validated.json()["status"], "ACTIVE")
        self.assertEqual(
            validated.json()["authority_validation_state"],
            "APPROVED",
        )
        self.assertTrue(self.staff_provisioner.created["new-staff-1"]["validated"])

        stale_claim = self.client.get(
            "/v1/access/me",
            headers=self.headers("new-staff-pending-token"),
        )
        self.assertEqual(stale_claim.json()["access_state"], "PENDING")
        self.assertEqual(
            stale_claim.json()["reason"],
            "STAFF_VALIDATED_CLAIM_REQUIRED",
        )
        authorized = self.client.get(
            "/v1/access/me",
            headers=self.headers("new-staff-validated-token"),
        )
        self.assertEqual(authorized.json()["access_state"], "AUTHORIZED")
        self.assertEqual(authorized.json()["role"], "support")

        staff_list = self.client.get(
            "/v1/admin/staff-accounts",
            headers=self.headers("admin-token"),
        )
        self.assertEqual(staff_list.status_code, 200, staff_list.text)
        listed = staff_list.json()["accounts"]
        self.assertEqual(
            {item["role"] for item in listed},
            {"admin", "support", "security"},
        )
        self.assertEqual(
            sum(item["protection_level"] == "SYSTEM" for item in listed),
            3,
        )

    def test_staff_creation_rejects_injected_permissions_and_stale_admin(self) -> None:
        injected = self.client.post(
            "/v1/admin/staff-accounts",
            headers=self.headers("admin-token"),
            json={
                "email": "seguranca-extra@example.test",
                "display_name": "Segurança Extra",
                "role": "security",
                "permissions": ["admin.panel.access"],
                "status": "ACTIVE",
            },
        )
        self.assertEqual(injected.status_code, 422, injected.text)

        stale = self.client.post(
            "/v1/admin/staff-accounts",
            headers=self.headers("stale-admin-token"),
            json={
                "email": "admin-extra@example.test",
                "display_name": "Admin Extra",
                "role": "admin",
            },
        )
        self.assertEqual(stale.status_code, 403, stale.text)
        self.assertEqual(
            stale.json()["code"],
            "RECENT_AUTHENTICATION_REQUIRED",
        )

    def test_support_provisions_institution_with_fixed_role_and_recent_authentication(self) -> None:
        created = self.client.post(
            "/v1/support/institutions",
            headers=self.headers("support-token"),
            json={
                "email": "biblioteca@pinhais.example",
                "name": "Biblioteca de Pinhais",
                "description": "Instituicao criada pelo suporte",
                "city": "Pinhais",
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        body = created.json()
        account = self.store.get_access_account(body["firebase_uid"])
        assert account is not None
        self.assertEqual(account.role, "institution")
        self.assertEqual(account.permissions, tuple(sorted(default_permissions("institution"))))
        self.assertEqual(
            self.institution_provisioner.created[body["firebase_uid"]]["claims"],
            {"role": "institution", "admin": False},
        )
        event = self.store.access_audit_events[-1]
        self.assertEqual(event.event_type, "INSTITUTION_PROVISIONED")
        self.assertEqual(event.actor_uid, "support-uid")
        self.assertEqual(event.target_uid, body["firebase_uid"])

        conflict = self.client.post(
            "/v1/support/institutions",
            headers=self.headers("support-token"),
            json={
                "email": "institution-uid@example.test",
                "name": "Identidade que sera revertida",
            },
        )
        self.assertEqual(conflict.status_code, 409, conflict.text)
        self.assertEqual(conflict.json()["code"], "INSTITUTION_ACCOUNT_EXISTS")
        self.assertIn("new-institution-2", self.institution_provisioner.rolled_back)
        self.assertNotIn("new-institution-2", self.institution_provisioner.created)

        injected = self.client.post(
            "/v1/support/institutions",
            headers=self.headers("support-token"),
            json={
                "email": "injetada-suporte@example.test",
                "name": "Conta injetada pelo suporte",
                "role": "admin",
                "permissions": ["admin.panel.access"],
                "password": "nao-deve-ser-aceita",
            },
        )
        self.assertEqual(injected.status_code, 422, injected.text)

        wrong_role = self.client.post(
            "/v1/support/institutions",
            headers=self.headers("admin-token"),
            json={"email": "admin-na-rota-suporte@example.test", "name": "Rota errada"},
        )
        self.assertEqual(wrong_role.status_code, 403, wrong_role.text)
        self.assertEqual(wrong_role.json()["code"], "SUPPORT_ACCESS_REQUIRED")

        stale = self.client.post(
            "/v1/support/institutions",
            headers=self.headers("stale-support-token"),
            json={"email": "sessao-antiga@example.test", "name": "Sessao antiga"},
        )
        self.assertEqual(stale.status_code, 403, stale.text)
        self.assertEqual(stale.json()["code"], "RECENT_AUTHENTICATION_REQUIRED")

        support = self.store.get_access_account("support-uid")
        assert support is not None
        self.store.set_access_account(
            replace(
                support,
                permissions=tuple(
                    permission
                    for permission in support.permissions
                    if permission != "support.institutions.create"
                ),
            )
        )
        denied = self.client.post(
            "/v1/support/institutions",
            headers=self.headers("support-token"),
            json={"email": "sem-permissao@example.test", "name": "Sem permissao"},
        )
        self.assertEqual(denied.status_code, 403, denied.text)
        self.assertEqual(denied.json()["code"], "ACCOUNT_PERMISSION_REQUIRED")

    def test_public_institution_application_is_reviewed_and_approved_by_support(self) -> None:
        account_count = len(self.store.access_accounts)
        submitted = self.client.post(
            "/v1/public/institution-applications",
            json={
                "organization_type": "NGO",
                "organization_name": "Instituto Rotas Locais",
                "contact_name": "Responsavel da Instituicao",
                "email": "CONTATO@ROTAS.EXAMPLE",
                "phone": "(41) 99999-1234",
                "registration_number": "REG-123456",
                "city": "Pinhais",
                "state": "pr",
                "website_or_social": "https://example.test/rotas",
                "description": "Organizacao comunitaria dedicada ao turismo e comercio local.",
                "privacy_accepted": True,
            },
        )
        self.assertEqual(submitted.status_code, 201, submitted.text)
        application_id = submitted.json()["application_id"]
        self.assertEqual(submitted.json()["status"], "NEW")
        self.assertEqual(len(self.store.access_accounts), account_count)

        unauthenticated = self.client.get("/v1/support/institution-applications")
        self.assertEqual(unauthenticated.status_code, 401, unauthenticated.text)
        wrong_role = self.client.get(
            "/v1/support/institution-applications",
            headers=self.headers("admin-token"),
        )
        self.assertEqual(wrong_role.status_code, 403, wrong_role.text)

        listed = self.client.get(
            "/v1/support/institution-applications",
            headers=self.headers("support-token"),
        )
        self.assertEqual(listed.status_code, 200, listed.text)
        application = listed.json()["applications"][0]
        self.assertEqual(application["application_id"], application_id)
        self.assertEqual(application["email"], "contato@rotas.example")
        self.assertEqual(application["state"], "PR")
        self.assertIsNone(application["provisioned_uid"])

        contacted = self.client.patch(
            f"/v1/support/institution-applications/{application_id}",
            headers=self.headers("support-token"),
            json={"status": "CONTACTED", "support_notes": "Dados iniciais conferidos."},
        )
        self.assertEqual(contacted.status_code, 200, contacted.text)
        self.assertEqual(contacted.json()["status"], "CONTACTED")
        self.assertEqual(len(self.store.access_accounts), account_count)

        approved = self.client.patch(
            f"/v1/support/institution-applications/{application_id}",
            headers=self.headers("support-token"),
            json={"status": "APPROVED", "support_notes": "Documentos conferidos pelo suporte."},
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        approval = approved.json()
        self.assertEqual(approval["status"], "APPROVED")
        self.assertEqual(approval["reviewed_by_uid"], "support-uid")
        provisioned_uid = approval["provisioned_uid"]
        account = self.store.get_access_account(provisioned_uid)
        assert account is not None
        self.assertEqual(account.role, "institution")
        self.assertIn((provisioned_uid, "contato@rotas.example"), self.email_verification_sender.calls)

        repeated = self.client.patch(
            f"/v1/support/institution-applications/{application_id}",
            headers=self.headers("support-token"),
            json={"status": "APPROVED"},
        )
        self.assertEqual(repeated.status_code, 409, repeated.text)
        self.assertEqual(repeated.json()["code"], "INSTITUTION_APPLICATION_NOT_APPROVABLE")

    def test_institution_application_approval_rolls_back_when_first_access_email_fails(self) -> None:
        submitted = self.client.post(
            "/v1/public/institution-applications",
            json={
                "organization_type": "COMPANY",
                "organization_name": "Empresa sem entrega",
                "contact_name": "Contato Responsavel",
                "email": "falha-email@example.test",
                "city": "Pinhais",
                "state": "PR",
                "description": "Empresa interessada em participar das iniciativas do LiberRotas.",
                "privacy_accepted": True,
            },
        )
        self.assertEqual(submitted.status_code, 201, submitted.text)
        application_id = submitted.json()["application_id"]
        self.email_verification_sender.result = "SMTP_FAILED"

        approval = self.client.patch(
            f"/v1/support/institution-applications/{application_id}",
            headers=self.headers("support-token"),
            json={"status": "APPROVED"},
        )
        self.assertEqual(approval.status_code, 503, approval.text)
        self.assertEqual(approval.json()["code"], "INSTITUTION_FIRST_ACCESS_EMAIL_FAILED")
        application = next(iter(self.store.institution_applications.values()))
        self.assertEqual(application.status, "NEW")
        self.assertIsNone(application.provisioned_uid)
        self.assertIn("new-institution-1", self.institution_provisioner.rolled_back)
        self.assertIsNone(self.store.get_access_account("new-institution-1"))

    def test_institution_groups_are_scoped_to_authenticated_owner(self) -> None:
        injected = self.client.post(
            "/v1/institution/groups",
            headers=self.headers("institution-token"),
            json={
                "name": "Grupo adulterado",
                "owner_uid": "institution-other-uid",
                "status": "CLOSED",
            },
        )
        self.assertEqual(injected.status_code, 422, injected.text)

        created = self.client.post(
            "/v1/institution/groups",
            headers=self.headers("institution-token"),
            json={
                "name": "Artesas de Pinhais",
                "description": "Rede de colaboracao",
                "city": "Pinhais",
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        group = created.json()
        self.assertEqual(group["owner_uid"], "institution-uid")
        self.assertEqual(group["status"], "ACTIVE")
        self.assertIsNone(group["closed_at"])

        other = self.client.post(
            "/v1/institution/groups",
            headers=self.headers("institution-other-token"),
            json={"name": "Grupo de outra instituicao"},
        )
        self.assertEqual(other.status_code, 201, other.text)

        own_list = self.client.get(
            "/v1/institution/groups",
            headers=self.headers("institution-token"),
        )
        self.assertEqual(own_list.status_code, 200, own_list.text)
        self.assertEqual(
            {item["group_id"] for item in own_list.json()["groups"]},
            {group["group_id"]},
        )

        foreign_close = self.client.post(
            f"/v1/institution/groups/{group['group_id']}/close",
            headers=self.headers("institution-other-token"),
        )
        self.assertEqual(foreign_close.status_code, 404, foreign_close.text)
        self.assertEqual(
            foreign_close.json()["code"],
            "INSTITUTION_GROUP_NOT_FOUND_OR_NOT_OWNED",
        )

        closed = self.client.post(
            f"/v1/institution/groups/{group['group_id']}/close",
            headers=self.headers("institution-token"),
        )
        self.assertEqual(closed.status_code, 200, closed.text)
        self.assertEqual(closed.json()["status"], "CLOSED")
        self.assertIsNotNone(closed.json()["closed_at"])

        wrong_role = self.client.get(
            "/v1/institution/groups",
            headers=self.headers("visit-token"),
        )
        self.assertEqual(wrong_role.status_code, 403, wrong_role.text)
        self.assertEqual(wrong_role.json()["code"], "INSTITUTION_ACCESS_REQUIRED")

        institution_access = self.store.get_access_account("institution-uid")
        assert institution_access is not None
        self.store.set_access_account(
            replace(
                institution_access,
                permissions=tuple(
                    permission
                    for permission in institution_access.permissions
                    if permission != "institution.groups.manage"
                ),
            )
        )
        denied = self.client.post(
            "/v1/institution/groups",
            headers=self.headers("institution-token"),
            json={"name": "Sem permissao"},
        )
        self.assertEqual(denied.status_code, 403, denied.text)

    def test_institution_profile_patch_is_own_and_strictly_field_limited(self) -> None:
        current = self.client.get(
            "/v1/institution/profile",
            headers=self.headers("institution-token"),
        )
        self.assertEqual(current.status_code, 200, current.text)
        self.assertEqual(current.json()["firebase_uid"], "institution-uid")

        other_before = self.store.institution_profiles["institution-other-uid"]
        updated = self.client.patch(
            "/v1/institution/profile",
            headers=self.headers("institution-token"),
            json={
                "name": "Instituicao Cultural de Pinhais",
                "description": None,
                "city": "Curitiba",
            },
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        body = updated.json()
        self.assertEqual(body["firebase_uid"], "institution-uid")
        self.assertEqual(body["name"], "Instituicao Cultural de Pinhais")
        self.assertIsNone(body["description"])
        self.assertEqual(body["city"], "Curitiba")
        self.assertEqual(
            self.store.institution_profiles["institution-other-uid"],
            other_before,
        )

        for invalid_payload in (
            {},
            {"name": None},
            {"email": "adulterado@example.test"},
            {"status": "SUSPENDED"},
            {"role": "admin"},
        ):
            invalid = self.client.patch(
                "/v1/institution/profile",
                headers=self.headers("institution-token"),
                json=invalid_payload,
            )
            self.assertEqual(invalid.status_code, 422, invalid.text)

        wrong_role = self.client.get(
            "/v1/institution/profile",
            headers=self.headers("visit-token"),
        )
        self.assertEqual(wrong_role.status_code, 403, wrong_role.text)
        self.assertEqual(wrong_role.json()["code"], "INSTITUTION_ACCESS_REQUIRED")

        institution = self.store.get_access_account("institution-uid")
        assert institution is not None
        self.store.set_access_account(
            replace(
                institution,
                permissions=tuple(
                    permission
                    for permission in institution.permissions
                    if permission != "institution.profile.manage"
                ),
            )
        )
        denied = self.client.get(
            "/v1/institution/profile",
            headers=self.headers("institution-token"),
        )
        self.assertEqual(denied.status_code, 403, denied.text)

    def test_institution_report_counts_only_own_groups(self) -> None:
        first = self.client.post(
            "/v1/institution/groups",
            headers=self.headers("institution-token"),
            json={"name": "Grupo ativo da instituicao"},
        )
        second = self.client.post(
            "/v1/institution/groups",
            headers=self.headers("institution-token"),
            json={"name": "Grupo encerrado da instituicao"},
        )
        foreign = self.client.post(
            "/v1/institution/groups",
            headers=self.headers("institution-other-token"),
            json={"name": "Grupo de outra instituicao"},
        )
        for response in (first, second, foreign):
            self.assertEqual(response.status_code, 201, response.text)
        closed = self.client.post(
            f"/v1/institution/groups/{second.json()['group_id']}/close",
            headers=self.headers("institution-token"),
        )
        self.assertEqual(closed.status_code, 200, closed.text)

        report = self.client.get(
            "/v1/institution/reports/summary",
            headers=self.headers("institution-token"),
        )
        self.assertEqual(report.status_code, 200, report.text)
        body = report.json()
        self.assertEqual(body["total_groups"], 2)
        self.assertEqual(body["active_groups"], 1)
        self.assertEqual(body["closed_groups"], 1)
        self.assertIsNotNone(body["last_group_created_at"])
        self.assertIn("generated_at", body)

        wrong_role = self.client.get(
            "/v1/institution/reports/summary",
            headers=self.headers("support-token"),
        )
        self.assertEqual(wrong_role.status_code, 403, wrong_role.text)

        institution = self.store.get_access_account("institution-uid")
        assert institution is not None
        self.store.set_access_account(
            replace(
                institution,
                permissions=tuple(
                    permission
                    for permission in institution.permissions
                    if permission != "institution.reports.read"
                ),
            )
        )
        denied = self.client.get(
            "/v1/institution/reports/summary",
            headers=self.headers("institution-token"),
        )
        self.assertEqual(denied.status_code, 403, denied.text)

    def test_institution_membership_requires_invitation_and_seller_acceptance(self) -> None:
        profile = self.save_public_profile("entre-token", "Vendedor Unico da Feira")
        self.assertEqual(profile.status_code, 200, profile.text)
        group = self.client.post(
            "/v1/institution/groups",
            headers=self.headers("institution-token"),
            json={"name": "Rede da Instituicao Principal"},
        ).json()

        injected = self.client.post(
            f"/v1/institution/groups/{group['group_id']}/invitations",
            headers=self.headers("institution-token"),
            json={"seller_name": "Vendedor Unico da Feira", "seller_uid": "visit-uid"},
        )
        self.assertEqual(injected.status_code, 422, injected.text)

        invited = self.client.post(
            f"/v1/institution/groups/{group['group_id']}/invitations",
            headers=self.headers("institution-token"),
            json={"seller_name": "  vendedor unico da feira  "},
        )
        self.assertEqual(invited.status_code, 201, invited.text)
        invitation = invited.json()
        self.assertEqual(invitation["seller_uid"], "entre-uid")
        self.assertEqual(invitation["status"], "PENDING")

        repeated = self.client.post(
            f"/v1/institution/groups/{group['group_id']}/invitations",
            headers=self.headers("institution-token"),
            json={"seller_name": "Vendedor Unico da Feira"},
        )
        self.assertEqual(repeated.status_code, 201, repeated.text)
        self.assertEqual(repeated.json()["membership_id"], invitation["membership_id"])

        foreign_list = self.client.get(
            f"/v1/institution/groups/{group['group_id']}/members",
            headers=self.headers("institution-other-token"),
        )
        self.assertEqual(foreign_list.status_code, 404, foreign_list.text)

        own_invitations = self.client.get(
            "/v1/entrepreneur/institution-invitations?status=PENDING",
            headers=self.headers("entre-token"),
        )
        self.assertEqual(own_invitations.status_code, 200, own_invitations.text)
        self.assertEqual(
            own_invitations.json()["memberships"][0]["membership_id"],
            invitation["membership_id"],
        )

        institution_cannot_accept = self.client.post(
            f"/v1/entrepreneur/institution-invitations/{invitation['membership_id']}/accept",
            headers=self.headers("institution-token"),
        )
        self.assertEqual(institution_cannot_accept.status_code, 403, institution_cannot_accept.text)

        accepted = self.client.post(
            f"/v1/entrepreneur/institution-invitations/{invitation['membership_id']}/accept",
            headers=self.headers("entre-token"),
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(accepted.json()["status"], "ACTIVE")

        other_group = self.client.post(
            "/v1/institution/groups",
            headers=self.headers("institution-other-token"),
            json={"name": "Rede da Instituicao Secundaria"},
        ).json()
        other_invitation = self.client.post(
            f"/v1/institution/groups/{other_group['group_id']}/invitations",
            headers=self.headers("institution-other-token"),
            json={"seller_name": "Vendedor Unico da Feira"},
        )
        self.assertEqual(other_invitation.status_code, 201, other_invitation.text)
        conflicting_accept = self.client.post(
            f"/v1/entrepreneur/institution-invitations/{other_invitation.json()['membership_id']}/accept",
            headers=self.headers("entre-token"),
        )
        self.assertEqual(conflicting_accept.status_code, 409, conflicting_accept.text)
        self.assertEqual(
            conflicting_accept.json()["code"],
            "SELLER_ALREADY_HAS_ACTIVE_MEMBERSHIP",
        )

        foreign_remove = self.client.post(
            f"/v1/institution/groups/{group['group_id']}/members/{invitation['membership_id']}/remove",
            headers=self.headers("institution-other-token"),
        )
        self.assertEqual(foreign_remove.status_code, 404, foreign_remove.text)
        removed = self.client.post(
            f"/v1/institution/groups/{group['group_id']}/members/{invitation['membership_id']}/remove",
            headers=self.headers("institution-token"),
        )
        self.assertEqual(removed.status_code, 200, removed.text)
        self.assertEqual(removed.json()["status"], "REMOVED")

        accepted_other = self.client.post(
            f"/v1/entrepreneur/institution-invitations/{other_invitation.json()['membership_id']}/accept",
            headers=self.headers("entre-token"),
        )
        self.assertEqual(accepted_other.status_code, 200, accepted_other.text)
        self.assertEqual(accepted_other.json()["status"], "ACTIVE")

    def test_institution_sales_report_uses_membership_window_and_snapshot_values(self) -> None:
        self.assertEqual(
            self.save_public_profile("entre-token", "Vendedor do Relatorio").status_code,
            200,
        )
        group = self.client.post(
            "/v1/institution/groups",
            headers=self.headers("institution-token"),
            json={"name": "Grupo com Relatorio"},
        ).json()
        invitation = self.client.post(
            f"/v1/institution/groups/{group['group_id']}/invitations",
            headers=self.headers("institution-token"),
            json={"seller_name": "Vendedor do Relatorio"},
        ).json()
        accepted = self.client.post(
            f"/v1/entrepreneur/institution-invitations/{invitation['membership_id']}/accept",
            headers=self.headers("entre-token"),
        ).json()
        active_from = datetime.fromisoformat(accepted["active_from"])
        inside = active_from + timedelta(seconds=10)
        before = active_from - timedelta(seconds=10)
        self.store.redemptions[("report-offer-1", "buyer-1")] = {
            "redemption_id": "report-redemption-1",
            "merchant_uid": "entre-uid",
            "status": "REDEEMED",
            "committed_at": inside,
            "quantity": 1,
            "currency": "BRL",
            "original_amount_minor": 1000,
            "final_amount_minor": 800,
            "buyer_uid": "buyer-secret-1",
            "device_key_id": "device-secret-1",
            "token_ref": "token-secret-1",
        }
        self.store.redemptions[("report-offer-2", "buyer-2")] = {
            "redemption_id": "report-redemption-2",
            "merchant_uid": "entre-uid",
            "status": "REDEEMED",
            "committed_at": inside + timedelta(seconds=1),
            "quantity": 1,
            "currency": "USD",
            "original_amount_minor": 500,
            "final_amount_minor": 450,
        }
        self.store.redemptions[("report-offer-3", "buyer-3")] = {
            "redemption_id": "report-redemption-3",
            "merchant_uid": "entre-uid",
            "status": "REDEEMED",
            "committed_at": inside + timedelta(seconds=2),
            "quantity": 1,
            "currency": "BRL",
            "original_amount_minor": None,
            "final_amount_minor": None,
            "snapshot_quality": "LEGACY_UNAVAILABLE",
        }
        self.store.redemptions[("report-offer-old", "buyer-4")] = {
            "redemption_id": "report-redemption-old",
            "merchant_uid": "entre-uid",
            "status": "REDEEMED",
            "committed_at": before,
            "quantity": 1,
            "currency": "BRL",
            "original_amount_minor": 9999,
            "final_amount_minor": 1,
        }

        report = self.client.get(
            "/v1/institution/reports/sales",
            headers=self.headers("institution-token"),
            params={
                "group_id": group["group_id"],
                "from": (active_from - timedelta(minutes=1)).isoformat(),
                "to": (inside + timedelta(minutes=1)).isoformat(),
            },
        )
        self.assertEqual(report.status_code, 200, report.text)
        body = report.json()
        self.assertEqual(body["confirmed_redemptions"], 3)
        self.assertEqual(body["units_sold"], 3)
        self.assertEqual(body["amounts_unavailable_count"], 1)
        totals = {item["currency"]: item for item in body["totals_by_currency"]}
        self.assertEqual(totals["BRL"]["gross_original_amount_minor"], 1000)
        self.assertEqual(totals["BRL"]["gross_final_amount_minor"], 800)
        self.assertEqual(totals["USD"]["gross_final_amount_minor"], 450)
        self.assertEqual(body["sellers"][0]["confirmed_redemptions"], 3)
        self.assertTrue(
            {"membership_id", "group_id", "seller_uid"}.isdisjoint(body["sellers"][0]),
            body["sellers"][0],
        )
        self.assertIn("nao comprova", body["financial_notice"])
        sensitive = {"buyer_uid", "device_key_id", "token_ref", "operation_id", "pix_key"}
        self.assertTrue(sensitive.isdisjoint(nested_keys(body)))

        foreign = self.client.get(
            "/v1/institution/reports/sales",
            headers=self.headers("institution-other-token"),
            params={"group_id": group["group_id"]},
        )
        self.assertEqual(foreign.status_code, 404, foreign.text)

        too_large = self.client.get(
            "/v1/institution/reports/sales",
            headers=self.headers("institution-token"),
            params={
                "from": (active_from - timedelta(days=367)).isoformat(),
                "to": active_from.isoformat(),
            },
        )
        self.assertEqual(too_large.status_code, 422, too_large.text)
        self.assertEqual(too_large.json()["code"], "REPORT_PERIOD_TOO_LARGE")

    def test_funded_event_allocation_activation_and_amount_due_report(self) -> None:
        self.assertEqual(
            self.save_public_profile(
                "entre-token",
                "Vendedor do Evento Financiado",
            ).status_code,
            200,
        )
        group = self.client.post(
            "/v1/institution/groups",
            headers=self.headers("institution-token"),
            json={"name": "Grupo do Evento Financiado"},
        ).json()
        invitation = self.client.post(
            f"/v1/institution/groups/{group['group_id']}/invitations",
            headers=self.headers("institution-token"),
            json={"seller_name": "Vendedor do Evento Financiado"},
        ).json()
        accepted = self.client.post(
            f"/v1/entrepreneur/institution-invitations/{invitation['membership_id']}/accept",
            headers=self.headers("entre-token"),
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        first_product_id = self.prepare_product(price_minor=1_000)
        second_product_id = self.prepare_product(price_minor=500)
        now = datetime.now(timezone.utc)

        created = self.client.post(
            "/v1/institution/funded-events",
            headers=self.headers("institution-token"),
            json={
                "group_id": group["group_id"],
                "name": "Feira financiada de julho",
                "description": "Verba promocional do evento",
                "funding_source": "DONATION",
                "budget_amount_minor": 1_000,
                "currency": "BRL",
                "end_mode": "TIME",
                "starts_at": (now - timedelta(minutes=1)).isoformat(),
                "ends_at": (now + timedelta(days=1)).isoformat(),
                "coupon_limit": None,
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        event = created.json()
        self.assertEqual(event["status"], "DRAFT")
        self.assertEqual(event["seller_allocations"][0]["allocated_amount_minor"], 1_000)
        self.assertEqual(event["seller_allocations"][0]["allocation_mode"], "EQUAL")
        self.assertFalse(event["seller_allocations"][0]["product_allocation_configured"])

        entrepreneur_view = self.client.get(
            "/v1/entrepreneur/funded-events",
            headers=self.headers("entre-token"),
        )
        self.assertEqual(entrepreneur_view.status_code, 200, entrepreneur_view.text)
        self.assertEqual(
            entrepreneur_view.json()["events"][0]["allocated_amount_minor"],
            1_000,
        )
        self.assertNotIn(
            "seller_allocations",
            entrepreneur_view.json()["events"][0],
        )

        mismatch = self.client.put(
            f"/v1/entrepreneur/funded-events/{event['event_id']}/product-allocations",
            headers=self.headers("entre-token"),
            json={
                "allocations": [
                    {
                        "product_id": first_product_id,
                        "allocated_amount_minor": 999,
                    },
                    {
                        "product_id": second_product_id,
                        "allocated_amount_minor": 0,
                    },
                ]
            },
        )
        self.assertEqual(mismatch.status_code, 409, mismatch.text)
        self.assertEqual(
            mismatch.json()["code"],
            "INSTITUTION_EVENT_PRODUCT_TOTAL_MISMATCH",
        )

        configured = self.client.put(
            f"/v1/entrepreneur/funded-events/{event['event_id']}/product-allocations",
            headers=self.headers("entre-token"),
            json={
                "allocations": [
                    {
                        "product_id": first_product_id,
                        "allocated_amount_minor": 700,
                    },
                    {
                        "product_id": second_product_id,
                        "allocated_amount_minor": 300,
                    },
                ]
            },
        )
        self.assertEqual(configured.status_code, 200, configured.text)
        self.assertTrue(configured.json()["product_allocation_configured"])

        activated = self.client.post(
            f"/v1/institution/funded-events/{event['event_id']}/activate",
            headers=self.headers("institution-token"),
        )
        self.assertEqual(activated.status_code, 200, activated.text)
        self.assertEqual(activated.json()["status"], "ACTIVE")
        committed_at = datetime.now(timezone.utc)
        self.store.redemptions[("funded-offer-1", "funded-buyer-1")] = {
            "redemption_id": "funded-redemption-1",
            "merchant_uid": "entre-uid",
            "product_id": first_product_id,
            "status": "REDEEMED",
            "committed_at": committed_at,
            "quantity": 1,
            "currency": "BRL",
            "original_amount_minor": 1_000,
            "final_amount_minor": 800,
            "buyer_uid": "must-not-leak",
        }
        self.store.redemptions[("funded-offer-2", "funded-buyer-2")] = {
            "redemption_id": "funded-redemption-2",
            "merchant_uid": "entre-uid",
            "product_id": second_product_id,
            "status": "REDEEMED",
            "committed_at": committed_at,
            "quantity": 2,
            "currency": "BRL",
            "original_amount_minor": 500,
            "final_amount_minor": 450,
        }
        report = self.client.get(
            f"/v1/institution/funded-events/{event['event_id']}/report",
            headers=self.headers("institution-token"),
        )
        self.assertEqual(report.status_code, 200, report.text)
        body = report.json()
        self.assertEqual(body["confirmed_redemptions"], 2)
        self.assertEqual(body["units_sold"], 3)
        self.assertEqual(body["discount_used_minor"], 250)
        self.assertEqual(body["amount_due_minor"], 250)
        self.assertEqual(body["remaining_budget_minor"], 750)
        self.assertEqual(body["sellers"][0]["amount_due_minor"], 250)
        self.assertTrue(
            {"buyer_uid", "device_key_id", "token_ref", "pix_key"}.isdisjoint(
                nested_keys(body)
            )
        )

        entrepreneur_report = self.client.get(
            f"/v1/entrepreneur/funded-events/{event['event_id']}/report",
            headers=self.headers("entre-token"),
        )
        self.assertEqual(
            entrepreneur_report.status_code,
            200,
            entrepreneur_report.text,
        )
        entrepreneur_body = entrepreneur_report.json()
        self.assertEqual(entrepreneur_body["confirmed_redemptions"], 2)
        self.assertEqual(entrepreneur_body["units_sold"], 3)
        self.assertEqual(entrepreneur_body["amount_due_minor"], 250)
        self.assertEqual(
            {
                item["product_id"]: item["amount_due_minor"]
                for item in entrepreneur_body["products"]
            },
            {
                first_product_id: 200,
                second_product_id: 50,
            },
        )
        self.assertNotIn("sellers", entrepreneur_body)
        self.assertTrue(
            {"buyer_uid", "device_key_id", "token_ref", "pix_key"}.isdisjoint(
                nested_keys(entrepreneur_body)
            )
        )
        foreign_entrepreneur_report = self.client.get(
            f"/v1/entrepreneur/funded-events/{event['event_id']}/report",
            headers=self.headers("entre-other-token"),
        )
        self.assertEqual(
            foreign_entrepreneur_report.status_code,
            404,
            foreign_entrepreneur_report.text,
        )

        foreign_report = self.client.get(
            f"/v1/institution/funded-events/{event['event_id']}/report",
            headers=self.headers("institution-other-token"),
        )
        self.assertEqual(foreign_report.status_code, 404, foreign_report.text)
        ended = self.client.post(
            f"/v1/institution/funded-events/{event['event_id']}/end",
            headers=self.headers("institution-token"),
        )
        self.assertEqual(ended.status_code, 200, ended.text)
        self.assertEqual(ended.json()["status"], "ENDED")
        self.assertEqual(ended.json()["end_reason"], "MANUAL")

    def test_funded_event_can_end_when_coupon_limit_is_reached(self) -> None:
        self.assertEqual(
            self.save_public_profile(
                "entre-token",
                "Vendedor do Evento por Cupons",
            ).status_code,
            200,
        )
        group = self.client.post(
            "/v1/institution/groups",
            headers=self.headers("institution-token"),
            json={"name": "Grupo do Evento por Cupons"},
        ).json()
        invitation = self.client.post(
            f"/v1/institution/groups/{group['group_id']}/invitations",
            headers=self.headers("institution-token"),
            json={"seller_name": "Vendedor do Evento por Cupons"},
        ).json()
        self.client.post(
            f"/v1/entrepreneur/institution-invitations/{invitation['membership_id']}/accept",
            headers=self.headers("entre-token"),
        )
        product_id = self.prepare_product(price_minor=1_000)
        now = datetime.now(timezone.utc)
        created = self.client.post(
            "/v1/institution/funded-events",
            headers=self.headers("institution-token"),
            json={
                "group_id": group["group_id"],
                "name": "Promoção até um cupom",
                "funding_source": "INSTITUTION_BUDGET",
                "budget_amount_minor": 500,
                "currency": "BRL",
                "end_mode": "COUPONS",
                "starts_at": (now - timedelta(minutes=1)).isoformat(),
                "coupon_limit": 1,
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        event_id = created.json()["event_id"]
        activated = self.client.post(
            f"/v1/institution/funded-events/{event_id}/activate",
            headers=self.headers("institution-token"),
        )
        self.assertEqual(activated.status_code, 200, activated.text)
        self.store.redemptions[("coupon-end-offer", "coupon-end-buyer")] = {
            "redemption_id": "coupon-end-redemption",
            "merchant_uid": "entre-uid",
            "product_id": product_id,
            "status": "REDEEMED",
            "committed_at": datetime.now(timezone.utc),
            "quantity": 1,
            "currency": "BRL",
            "original_amount_minor": 1_000,
            "final_amount_minor": 900,
        }
        refreshed = self.client.get(
            "/v1/institution/funded-events",
            headers=self.headers("institution-token"),
        )
        self.assertEqual(refreshed.status_code, 200, refreshed.text)
        ended = next(
            item
            for item in refreshed.json()["events"]
            if item["event_id"] == event_id
        )
        self.assertEqual(ended["status"], "ENDED")
        self.assertEqual(ended["end_reason"], "COUPONS")
        self.assertEqual(ended["current_coupon_redemptions"], 1)

    def test_closing_group_ends_active_memberships_and_pending_invitations(self) -> None:
        self.assertEqual(
            self.save_public_profile("entre-token", "Vendedor Encerramento").status_code,
            200,
        )
        group = self.client.post(
            "/v1/institution/groups",
            headers=self.headers("institution-token"),
            json={"name": "Grupo a Encerrar"},
        ).json()
        invitation = self.client.post(
            f"/v1/institution/groups/{group['group_id']}/invitations",
            headers=self.headers("institution-token"),
            json={"seller_name": "Vendedor Encerramento"},
        ).json()
        accepted = self.client.post(
            f"/v1/entrepreneur/institution-invitations/{invitation['membership_id']}/accept",
            headers=self.headers("entre-token"),
        ).json()
        self.client.post(
            f"/v1/entrepreneur/institution-memberships/{accepted['membership_id']}/leave",
            headers=self.headers("entre-token"),
        )
        pending = self.client.post(
            f"/v1/institution/groups/{group['group_id']}/invitations",
            headers=self.headers("institution-token"),
            json={"seller_name": "Vendedor Encerramento"},
        ).json()
        closed = self.client.post(
            f"/v1/institution/groups/{group['group_id']}/close",
            headers=self.headers("institution-token"),
        )
        self.assertEqual(closed.status_code, 200, closed.text)
        memberships = self.client.get(
            f"/v1/institution/groups/{group['group_id']}/members",
            headers=self.headers("institution-token"),
        ).json()["memberships"]
        by_id = {item["membership_id"]: item for item in memberships}
        self.assertEqual(by_id[accepted["membership_id"]]["status"], "LEFT")
        self.assertEqual(by_id[pending["membership_id"]]["status"], "REMOVED")

    def test_support_accounts_is_authorized_and_strictly_read_only(self) -> None:
        response = self.client.get(
            "/v1/support/accounts",
            headers=self.headers("support-token"),
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertGreater(len(response.json()["accounts"]), 0)
        exposed_keys = nested_keys(response.json())
        for forbidden in {
            "permissions",
            "pixKey",
            "pix_key",
            "device_key_id",
            "public_key_b64u",
            "ledger",
            "private_profile",
        }:
            self.assertNotIn(forbidden, exposed_keys)

        write_attempt = self.client.post(
            "/v1/support/accounts",
            headers=self.headers("support-token"),
            json={"status": "SUSPENDED"},
        )
        self.assertEqual(write_attempt.status_code, 405, write_attempt.text)

        wrong_role = self.client.get(
            "/v1/support/accounts",
            headers=self.headers("visit-token"),
        )
        self.assertEqual(wrong_role.status_code, 403, wrong_role.text)
        self.assertEqual(wrong_role.json()["code"], "SUPPORT_ACCESS_REQUIRED")

        support = self.store.get_access_account("support-uid")
        assert support is not None
        self.store.set_access_account(
            replace(
                support,
                permissions=tuple(
                    permission
                    for permission in support.permissions
                    if permission != "support.accounts.read"
                ),
            )
        )
        denied = self.client.get(
            "/v1/support/accounts",
            headers=self.headers("support-token"),
        )
        self.assertEqual(denied.status_code, 403, denied.text)

    def test_security_status_changes_preserve_role_permissions_and_protect_accounts(self) -> None:
        original_visitor = self.store.get_access_account("visit-uid")
        assert original_visitor is not None
        missing_reason = self.client.post(
            "/v1/security/accounts/visit-uid/status",
            headers=self.headers("security-token"),
            json={"status": "SUSPENDED"},
        )
        self.assertEqual(missing_reason.status_code, 422, missing_reason.text)
        self.assertEqual(self.store.get_access_account("visit-uid"), original_visitor)
        suspended = self.client.post(
            "/v1/security/accounts/visit-uid/status",
            headers=self.headers("security-token"),
            json={
                "status": "SUSPENDED",
                "reason": "Atividade suspeita confirmada pelo monitoramento.",
            },
        )
        self.assertEqual(suspended.status_code, 200, suspended.text)
        self.assertEqual(suspended.json()["status"], "SUSPENDED")
        self.assertEqual(suspended.json()["role"], original_visitor.role)
        self.assertEqual(
            suspended.json()["permissions"],
            list(original_visitor.permissions),
        )
        persisted = self.store.get_access_account("visit-uid")
        assert persisted is not None
        self.assertEqual(persisted.role, original_visitor.role)
        self.assertEqual(persisted.permissions, original_visitor.permissions)

        listing = self.client.get(
            "/v1/security/accounts",
            headers=self.headers("security-token"),
        )
        self.assertEqual(listing.status_code, 200, listing.text)
        recent = listing.json()["recent_events"][0]
        self.assertEqual(recent["event_type"], "ACCOUNT_STATUS_CHANGED")
        self.assertEqual(recent["target_uid"], "visit-uid")
        self.assertEqual(recent["previous_status"], "ACTIVE")
        self.assertEqual(recent["new_status"], "SUSPENDED")
        self.assertEqual(
            recent["reason"],
            "Atividade suspeita confirmada pelo monitoramento.",
        )

        for target_uid, expected_code in (
            ("admin-uid", "PROTECTED_ACCOUNT_STATUS_CHANGE"),
            ("security-uid", "SELF_STATUS_CHANGE_FORBIDDEN"),
        ):
            protected = self.client.post(
                f"/v1/security/accounts/{target_uid}/status",
                headers=self.headers("security-token"),
                json={
                    "status": "SUSPENDED",
                    "reason": "Tentativa de suspensao de conta protegida.",
                },
            )
            self.assertEqual(protected.status_code, 403, protected.text)
            self.assertEqual(protected.json()["code"], expected_code)

        self.store.set_access_account(
            AccessAccountRecord(
                "security-other-uid",
                "security-other@example.test",
                "security",
                "ACTIVE",
                False,
                default_permissions("security"),
            )
        )
        protected_security = self.client.post(
            "/v1/security/accounts/security-other-uid/status",
            headers=self.headers("security-token"),
            json={
                "status": "SUSPENDED",
                "reason": "Tentativa de suspensao de conta protegida.",
            },
        )
        self.assertEqual(protected_security.status_code, 403, protected_security.text)
        self.assertEqual(
            protected_security.json()["code"],
            "PROTECTED_ACCOUNT_STATUS_CHANGE",
        )

        self.store.set_access_account(
            AccessAccountRecord(
                "pending-uid",
                "pending@example.test",
                "visitor",
                "PENDING",
                False,
                default_permissions("visitor"),
            )
        )
        pending = self.client.post(
            "/v1/security/accounts/pending-uid/status",
            headers=self.headers("security-token"),
            json={
                "status": "ACTIVE",
                "reason": "Reativacao solicitada apos verificacao do incidente.",
            },
        )
        self.assertEqual(pending.status_code, 409, pending.text)
        self.assertEqual(pending.json()["code"], "ACCOUNT_STATUS_TRANSITION_FORBIDDEN")

        injected = self.client.post(
            "/v1/security/accounts/visit-uid/status",
            headers=self.headers("security-token"),
            json={
                "status": "ACTIVE",
                "reason": "Tentativa com campos administrativos injetados.",
                "role": "admin",
                "permissions": ["admin.panel.access"],
            },
        )
        self.assertEqual(injected.status_code, 422, injected.text)

        stale = self.client.post(
            "/v1/security/accounts/visit-uid/status",
            headers=self.headers("stale-security-token"),
            json={
                "status": "ACTIVE",
                "reason": "Reativacao solicitada apos verificacao do incidente.",
            },
        )
        self.assertEqual(stale.status_code, 403, stale.text)
        self.assertEqual(stale.json()["code"], "RECENT_AUTHENTICATION_REQUIRED")

        security = self.store.get_access_account("security-uid")
        assert security is not None
        self.store.set_access_account(
            replace(
                security,
                permissions=tuple(
                    permission
                    for permission in security.permissions
                    if permission != "security.incidents.manage"
                ),
            )
        )
        missing_permission = self.client.post(
            "/v1/security/accounts/visit-uid/status",
            headers=self.headers("security-token"),
            json={
                "status": "ACTIVE",
                "reason": "Reativacao solicitada apos verificacao do incidente.",
            },
        )
        self.assertEqual(missing_permission.status_code, 403, missing_permission.text)

    def test_security_monitoring_summary_has_health_counts_and_recent_events(self) -> None:
        changed = self.client.post(
            "/v1/security/accounts/visit-uid/status",
            headers=self.headers("security-token"),
            json={
                "status": "SUSPENDED",
                "reason": "Monitoramento detectou comportamento de acesso anormal.",
            },
        )
        self.assertEqual(changed.status_code, 200, changed.text)

        monitoring = self.client.get(
            "/v1/security/monitoring/summary?events_limit=1",
            headers=self.headers("security-token"),
        )
        self.assertEqual(monitoring.status_code, 200, monitoring.text)
        body = monitoring.json()
        self.assertEqual(body["accounts_total"], len(self.store.access_accounts))
        self.assertEqual(body["suspended_accounts"], 1)
        self.assertGreaterEqual(body["active_accounts"], 1)
        self.assertEqual(body["recent_events_total"], 1)
        self.assertIsNotNone(body["last_event_at"])
        self.assertEqual(len(body["recent_events"]), 1)
        self.assertEqual(
            body["recent_events"][0]["reason"],
            "Monitoramento detectou comportamento de acesso anormal.",
        )
        self.assertTrue(body["database_ok"])
        self.assertTrue(body["redis_ok"])
        self.assertIn("server_time_iso", body)
        for forbidden in {"public_key_b64u", "token_ref", "signature_b64u", "pix_key"}:
            self.assertNotIn(forbidden, nested_keys(body))

        wrong_role = self.client.get(
            "/v1/security/monitoring/summary",
            headers=self.headers("support-token"),
        )
        self.assertEqual(wrong_role.status_code, 403, wrong_role.text)
        self.assertEqual(wrong_role.json()["code"], "SECURITY_ACCESS_REQUIRED")

        security = self.store.get_access_account("security-uid")
        assert security is not None
        self.store.set_access_account(
            replace(
                security,
                permissions=tuple(
                    permission
                    for permission in security.permissions
                    if permission != "security.audit.read"
                ),
            )
        )
        panel_permission_is_not_sufficient = self.client.get(
            "/v1/security/monitoring/summary",
            headers=self.headers("security-token"),
        )
        self.assertEqual(
            panel_permission_is_not_sufficient.status_code,
            403,
            panel_permission_is_not_sufficient.text,
        )

    def test_security_trq_bec_status_exposes_sanitized_control_telemetry(self) -> None:
        status = self.client.get(
            "/v1/security/trq-bec/status",
            headers=self.headers("security-token"),
        )
        self.assertEqual(status.status_code, 200, status.text)
        body = status.json()
        self.assertEqual(body["policy_version"], "test-policy-1")
        self.assertEqual(body["environment"], "test")
        self.assertTrue(body["lab_suite_enabled"])
        self.assertTrue(body["token_revocation_checks_enabled"])
        self.assertTrue(body["access_validation_enforced"])
        self.assertTrue(body["audit_ledger_append_only"])
        self.assertEqual(body["official_accounts_total"], 3)
        self.assertEqual(body["privileged_accounts_pending_validation"], 0)
        self.assertEqual(body["latest_schema_migration"], "memory-test-store")
        self.assertIn("server_time_iso", body)
        for forbidden in {
            "password",
            "private_key",
            "signature_b64u",
            "token_ref",
            "pix_key",
        }:
            self.assertNotIn(forbidden, nested_keys(body))

        wrong_role = self.client.get(
            "/v1/security/trq-bec/status",
            headers=self.headers("admin-token"),
        )
        self.assertEqual(wrong_role.status_code, 403, wrong_role.text)

        security = self.store.get_access_account("security-uid")
        assert security is not None
        self.store.set_access_account(
            replace(
                security,
                permissions=tuple(
                    permission
                    for permission in security.permissions
                    if permission != "security.trq_bec.monitor"
                ),
            )
        )
        missing_permission = self.client.get(
            "/v1/security/trq-bec/status",
            headers=self.headers("security-token"),
        )
        self.assertEqual(missing_permission.status_code, 403)

    def test_community_writes_require_current_database_permission(self) -> None:
        place = self.client.post(
            "/v1/community/places",
            headers=self.headers("entre-token"),
            json={
                "name": "Feira do Centro",
                "address": "Rua de Pinhais, 100",
                "category": "feiras_livres",
                "latitude": -25.44,
                "longitude": -49.19,
            },
        )
        self.assertEqual(place.status_code, 201, place.text)
        self.assertEqual(place.json()["status"], "approved")
        place_id = place.json()["document_id"]
        self.assertEqual(self.community.places[place_id]["uid"], "entre-uid")

        duplicate_place = self.client.post(
            "/v1/community/places",
            headers=self.headers("entre-token"),
            json={
                "name": "Segundo ponto indevido",
                "address": "Rua de Pinhais, 101",
                "category": "artesanato",
                "latitude": -25.44,
                "longitude": -49.19,
            },
        )
        self.assertEqual(duplicate_place.status_code, 409, duplicate_place.text)
        self.assertEqual(duplicate_place.json()["code"], "CURATED_PLACE_ALREADY_EXISTS")

        forbidden_place_delete = self.client.delete(
            f"/v1/community/places/{place_id}",
            headers=self.headers("entre-other-token"),
        )
        self.assertEqual(forbidden_place_delete.status_code, 403, forbidden_place_delete.text)
        self.assertIn(place_id, self.community.places)

        deleted_place = self.client.delete(
            f"/v1/community/places/{place_id}",
            headers=self.headers("entre-token"),
        )
        self.assertEqual(deleted_place.status_code, 200, deleted_place.text)
        self.assertNotIn(place_id, self.community.places)

        starts_at_ms = int(time.time() * 1000) + 60_000
        fair = self.client.post(
            "/v1/community/live-fairs",
            headers=self.headers("entre-token"),
            json={
                "name": "Feira ao vivo",
                "address": "Avenida de Pinhais, 200, Centro",
                "latitude": -25.43,
                "longitude": -49.18,
                "starts_at_ms": starts_at_ms,
                "ends_at_ms": starts_at_ms + 3_600_000,
            },
        )
        self.assertEqual(fair.status_code, 201, fair.text)
        fair_id = fair.json()["document_id"]
        ended = self.client.post(
            f"/v1/community/live-fairs/{fair_id}/end",
            headers=self.headers("entre-token"),
        )
        self.assertEqual(ended.status_code, 200, ended.text)
        self.assertEqual(self.community.fairs[fair_id]["status"], "ended")

        forbidden_delete = self.client.delete(
            f"/v1/community/live-fairs/{fair_id}",
            headers=self.headers("entre-other-token"),
        )
        self.assertEqual(forbidden_delete.status_code, 403, forbidden_delete.text)
        self.assertIn(fair_id, self.community.fairs)

        deleted = self.client.delete(
            f"/v1/community/live-fairs/{fair_id}",
            headers=self.headers("entre-token"),
        )
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertEqual(deleted.json(), {"document_id": fair_id, "status": "deleted"})
        self.assertNotIn(fair_id, self.community.fairs)

        institution_fair = self.client.post(
            "/v1/community/live-fairs",
            headers=self.headers("institution-token"),
            json={
                "name": "Feira institucional",
                "address": "Rua da Instituicao, 10",
                "latitude": -25.42,
                "longitude": -49.17,
                "starts_at_ms": starts_at_ms,
                "ends_at_ms": starts_at_ms + 3_600_000,
            },
        )
        self.assertEqual(institution_fair.status_code, 201, institution_fair.text)
        institution_fair_id = institution_fair.json()["document_id"]

        institution_forbidden = self.client.delete(
            f"/v1/community/live-fairs/{institution_fair_id}",
            headers=self.headers("institution-other-token"),
        )
        self.assertEqual(institution_forbidden.status_code, 403, institution_forbidden.text)

        institution_deleted = self.client.delete(
            f"/v1/community/live-fairs/{institution_fair_id}",
            headers=self.headers("institution-token"),
        )
        self.assertEqual(institution_deleted.status_code, 200, institution_deleted.text)
        self.assertNotIn(institution_fair_id, self.community.fairs)

        missing_delete = self.client.delete(
            "/v1/community/live-fairs/fair-missing",
            headers=self.headers("entre-token"),
        )
        self.assertEqual(missing_delete.status_code, 404, missing_delete.text)

        visitor_attempt = self.client.post(
            "/v1/community/places",
            headers=self.headers("visit-token"),
            json={
                "name": "Ponto indevido",
                "address": "Rua Teste, 10",
                "category": "artesanato",
                "latitude": -25.44,
                "longitude": -49.19,
            },
        )
        self.assertEqual(visitor_attempt.status_code, 403, visitor_attempt.text)

        current = self.store.get_access_account("entre-uid")
        assert current is not None
        self.store.set_access_account(
            replace(
                current,
                permissions=tuple(
                    permission for permission in current.permissions if permission != "locations.publish"
                ),
            )
        )
        removed_permission = self.client.post(
            "/v1/community/places",
            headers=self.headers("entre-token"),
            json={
                "name": "Ponto sem permissão",
                "address": "Rua Teste, 11",
                "category": "artesanato",
                "latitude": -25.44,
                "longitude": -49.19,
            },
        )
        self.assertEqual(removed_permission.status_code, 403, removed_permission.text)

    def test_media_image_upload_confirm_publish_is_visible_and_owner_can_delete(
        self,
    ) -> None:
        raw_image = b"\xff\xd8\xff-liberrotas-original"
        authorized = self.client.post(
            "/v1/media/uploads",
            headers=self.headers("entre-token"),
            json={
                "entity_type": "post",
                "entity_id": None,
                "media_role": "post_image",
                "original_filename": "foto-feira.jpg",
                "content_type": "image/jpeg",
                "size_bytes": len(raw_image),
                "client_request_id": "feed-image-request-001",
            },
        )
        self.assertEqual(authorized.status_code, 201, authorized.text)
        authorization = authorized.json()
        self.assertEqual(authorization["method"], "PUT")
        self.assertEqual(
            authorization["required_headers"]["Content-Type"],
            "image/jpeg",
        )
        self.assertNotIn("entre-token", authorization["upload_url"])
        self.assertNotIn("authorization", nested_keys(authorization))

        self.media_storage.simulate_signed_put(authorization, raw_image)
        processed_bytes = b"\xff\xd8\xff-liberrotas-processada"
        processed = ProcessedImage(
            data=processed_bytes,
            content_type="image/jpeg",
            width=1280,
            height=720,
            checksum_sha256=hashlib.sha256(processed_bytes).hexdigest(),
            variants=tuple(
                ProcessedImageVariant(
                    variant=name,
                    data=data,
                    content_type="image/webp",
                    width=width,
                    height=height,
                    checksum_sha256=hashlib.sha256(data).hexdigest(),
                )
                for name, data, width, height in (
                    ("thumbnail", b"thumbnail-webp", 320, 180),
                    ("display", b"display-webp", 1024, 576),
                )
            ),
        )
        with patch("trq_bec.server.service.process_image", return_value=processed):
            confirmed = self.client.post(
                f"/v1/media/uploads/{authorization['media_id']}/confirm",
                headers=self.headers("entre-token"),
            )
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertEqual(confirmed.json()["status"], "ready")
        self.assertEqual(confirmed.json()["detected_content_type"], "image/jpeg")
        self.assertEqual(confirmed.json()["width"], 1280)
        self.assertEqual(confirmed.json()["height"], 720)
        self.assertTrue(confirmed.json()["download_url"].startswith("https://"))
        variants = self.store.list_media_variants(authorization["media_id"])
        self.assertEqual([item.variant for item in variants], ["thumbnail", "display"])

        published = self.client.post(
            "/v1/community/posts",
            headers=self.headers("entre-token"),
            json={
                "text": "Foto compartilhada com todo o Feed",
                "media": {
                    "type": "image",
                    "media_id": authorization["media_id"],
                },
            },
        )
        self.assertEqual(published.status_code, 201, published.text)
        post_id = published.json()["document_id"]
        saved = self.community.posts[post_id]
        self.assertEqual(saved["request"].media.type, "image")
        self.assertEqual(
            saved["request"].media.media_id,
            authorization["media_id"],
        )
        self.assertEqual(
            self.store.get_media_asset(authorization["media_id"]).entity_id,
            post_id,
        )

        visible_to_visitor = self.client.get(
            f"/v1/media/{authorization['media_id']}",
            headers=self.headers("visit-token"),
        )
        self.assertEqual(visible_to_visitor.status_code, 200, visible_to_visitor.text)
        self.assertEqual(visible_to_visitor.json()["status"], "ready")
        self.assertTrue(visible_to_visitor.json()["download_url"].startswith("https://"))

        public_image = self.client.get(
            f"/v1/public/media/{authorization['media_id']}",
            follow_redirects=False,
        )
        self.assertEqual(public_image.status_code, 307, public_image.text)
        self.assertTrue(
            public_image.headers["location"].startswith(
                "https://storage.example.test/download/"
            )
        )
        self.assertIn("public, max-age=", public_image.headers["cache-control"])
        self.assertEqual(public_image.headers["referrer-policy"], "no-referrer")

        with (
            patch.object(
                self.store,
                "get_media_asset_with_variant",
                wraps=self.store.get_media_asset_with_variant,
            ) as variant_lookup,
            patch.object(
                self.store,
                "list_media_variants",
                wraps=self.store.list_media_variants,
            ) as variant_list,
        ):
            thumbnail = self.client.get(
                f"/v1/public/media/{authorization['media_id']}?variant=thumbnail",
                follow_redirects=False,
            )
        self.assertEqual(variant_lookup.call_count, 1)
        self.assertEqual(variant_list.call_count, 0)
        self.assertEqual(thumbnail.status_code, 307, thumbnail.text)
        self.assertIn(".thumbnail.webp", thumbnail.headers["location"])

        display = self.client.get(
            f"/v1/public/media/{authorization['media_id']}?variant=display",
            follow_redirects=False,
        )
        self.assertEqual(display.status_code, 307, display.text)
        self.assertIn(".display.webp", display.headers["location"])

        entity_media = self.client.get(
            "/v1/media",
            headers=self.headers("visit-token"),
            params={"entity_type": "post", "entity_id": post_id},
        )
        self.assertEqual(entity_media.status_code, 200, entity_media.text)
        self.assertEqual(
            [item["media_id"] for item in entity_media.json()["items"]],
            [authorization["media_id"]],
        )

        forbidden_delete = self.client.delete(
            f"/v1/media/{authorization['media_id']}",
            headers=self.headers("visit-token"),
        )
        self.assertEqual(forbidden_delete.status_code, 403, forbidden_delete.text)

        deleted = self.client.delete(
            f"/v1/media/{authorization['media_id']}",
            headers=self.headers("entre-token"),
        )
        self.assertEqual(deleted.status_code, 204, deleted.text)
        self.assertIn(authorization["object_key"], self.media_storage.deleted)
        self.assertTrue(any(key.endswith(".thumbnail.webp") for key in self.media_storage.deleted))
        self.assertTrue(any(key.endswith(".display.webp") for key in self.media_storage.deleted))
        self.assertEqual(self.store.list_media_variants(authorization["media_id"]), [])
        after_delete = self.client.get(
            f"/v1/media/{authorization['media_id']}",
            headers=self.headers("visit-token"),
        )
        self.assertEqual(after_delete.status_code, 404, after_delete.text)
        public_after_delete = self.client.get(
            f"/v1/public/media/{authorization['media_id']}",
            follow_redirects=False,
        )
        self.assertEqual(public_after_delete.status_code, 404, public_after_delete.text)

    def test_avatar_uses_owned_media_stable_profile_url_and_replaces_old_image(
        self,
    ) -> None:
        initial_profile = self.save_public_profile("visit-token", "Visitante Avatar")
        self.assertEqual(initial_profile.status_code, 200, initial_profile.text)

        external = self.save_public_profile(
            "visit-token",
            "Visitante Avatar",
            avatar_uri="https://tracker.example.test/pixel.png",
        )
        self.assertEqual(external.status_code, 422, external.text)
        self.assertEqual(external.json()["code"], "AVATAR_MEDIA_REFERENCE_REQUIRED")

        media_ids: list[str] = []
        for index in (1, 2):
            raw_image = f"\xff\xd8\xff-avatar-{index}".encode("latin1")
            authorized = self.client.post(
                "/v1/media/uploads",
                headers=self.headers("visit-token"),
                json={
                    "entity_type": "user",
                    "entity_id": "visit-uid",
                    "media_role": "avatar",
                    "original_filename": f"avatar-{index}.jpg",
                    "content_type": "image/jpeg",
                    "size_bytes": len(raw_image),
                    "client_request_id": f"avatar-replace-{index:03d}",
                },
            )
            self.assertEqual(authorized.status_code, 201, authorized.text)
            authorization = authorized.json()
            self.media_storage.simulate_signed_put(authorization, raw_image)
            processed_bytes = f"\xff\xd8\xff-avatar-ok-{index}".encode("latin1")
            processed = ProcessedImage(
                data=processed_bytes,
                content_type="image/jpeg",
                width=512,
                height=512,
                checksum_sha256=hashlib.sha256(processed_bytes).hexdigest(),
            )
            with patch("trq_bec.server.service.process_image", return_value=processed):
                confirmed = self.client.post(
                    f"/v1/media/uploads/{authorization['media_id']}/confirm",
                    headers=self.headers("visit-token"),
                )
            self.assertEqual(confirmed.status_code, 200, confirmed.text)
            media_ids.append(authorization["media_id"])

            updated = self.save_public_profile(
                "visit-token",
                "Visitante Avatar",
                avatar_uri=(
                    "https://api.liberrotas.com.br/v1/public/media/"
                    f"{authorization['media_id']}"
                ),
            )
            self.assertEqual(updated.status_code, 200, updated.text)

        stable_avatar = self.client.get(
            "/v1/public/profile/visit-uid/avatar",
            follow_redirects=False,
        )
        self.assertEqual(stable_avatar.status_code, 307, stable_avatar.text)
        self.assertIn("public, max-age=", stable_avatar.headers["cache-control"])
        self.assertEqual(self.store.get_media_asset(media_ids[0]).status, "deleted")
        self.assertEqual(self.store.get_media_asset(media_ids[1]).status, "ready")
        removed_old_url = self.client.get(
            f"/v1/public/media/{media_ids[0]}",
            follow_redirects=False,
        )
        self.assertEqual(removed_old_url.status_code, 404, removed_old_url.text)

    def test_media_upload_rejects_video_mime_size_role_and_legacy_url(self) -> None:
        base_payload = {
            "entity_type": "post",
            "entity_id": None,
            "media_role": "post_image",
            "original_filename": "foto.jpg",
            "content_type": "image/jpeg",
            "size_bytes": 1_024,
            "client_request_id": "media-validation-001",
        }

        video = self.client.post(
            "/v1/media/uploads",
            headers=self.headers("entre-token"),
            json={
                **base_payload,
                "original_filename": "video.mp4",
                "content_type": "video/mp4",
            },
        )
        self.assertEqual(video.status_code, 422, video.text)

        mime_mismatch = self.client.post(
            "/v1/media/uploads",
            headers=self.headers("entre-token"),
            json={
                **base_payload,
                "content_type": "image/png",
                "client_request_id": "media-validation-002",
            },
        )
        self.assertEqual(mime_mismatch.status_code, 422, mime_mismatch.text)
        self.assertEqual(
            mime_mismatch.json()["code"],
            "MEDIA_FILENAME_TYPE_MISMATCH",
        )

        oversized = self.client.post(
            "/v1/media/uploads",
            headers=self.headers("entre-token"),
            json={
                **base_payload,
                "size_bytes": 5_242_881,
                "client_request_id": "media-validation-003",
            },
        )
        self.assertEqual(oversized.status_code, 413, oversized.text)
        self.assertEqual(oversized.json()["code"], "MEDIA_FILE_TOO_LARGE")

        support_role = self.client.post(
            "/v1/media/uploads",
            headers=self.headers("support-token"),
            json={
                **base_payload,
                "client_request_id": "media-validation-004",
            },
        )
        self.assertEqual(support_role.status_code, 403, support_role.text)

        unauthenticated = self.client.post(
            "/v1/media/uploads",
            json=base_payload,
        )
        self.assertEqual(unauthenticated.status_code, 401, unauthenticated.text)

        legacy_public_url = self.client.post(
            "/v1/community/posts",
            headers=self.headers("entre-token"),
            json={
                "text": "Nao aceitar URL de midia enviada pelo cliente",
                "media": {
                    "type": "image",
                    "uri": "https://cdn.example.test/foto.jpg",
                },
            },
        )
        self.assertEqual(legacy_public_url.status_code, 422, legacy_public_url.text)

    def test_media_confirmation_rejects_changed_object_metadata(self) -> None:
        raw_image = b"\xff\xd8\xff-object-metadata"
        authorized = self.client.post(
            "/v1/media/uploads",
            headers=self.headers("visit-token"),
            json={
                "entity_type": "post",
                "entity_id": None,
                "media_role": "post_image",
                "original_filename": "visitante.jpg",
                "content_type": "image/jpeg",
                "size_bytes": len(raw_image),
                "client_request_id": "media-metadata-001",
            },
        )
        self.assertEqual(authorized.status_code, 201, authorized.text)
        authorization = authorized.json()
        self.media_storage.simulate_signed_put(authorization, raw_image)
        self.media_storage.objects[authorization["object_key"]][
            "content_type"
        ] = "image/png"

        confirmed = self.client.post(
            f"/v1/media/uploads/{authorization['media_id']}/confirm",
            headers=self.headers("visit-token"),
        )
        self.assertEqual(confirmed.status_code, 422, confirmed.text)
        self.assertEqual(confirmed.json()["code"], "MEDIA_OBJECT_TYPE_MISMATCH")
        self.assertNotIn(authorization["object_key"], self.media_storage.objects)
        self.assertEqual(
            self.store.get_media_asset(authorization["media_id"]).status,
            "rejected",
        )

    def test_media_confirmation_rejects_missing_object_and_size_mismatch(
        self,
    ) -> None:
        missing_bytes = b"\xff\xd8\xff-missing-object"
        missing = self.authorize_post_image(
            "visit-token",
            "media-missing-object-001",
            missing_bytes,
        )
        self.assertEqual(missing.status_code, 201, missing.text)
        missing_confirmation = self.client.post(
            f"/v1/media/uploads/{missing.json()['media_id']}/confirm",
            headers=self.headers("visit-token"),
        )
        self.assertEqual(
            missing_confirmation.status_code,
            409,
            missing_confirmation.text,
        )
        self.assertEqual(
            missing_confirmation.json()["code"],
            "MEDIA_OBJECT_NOT_FOUND",
        )

        expected_bytes = b"\xff\xd8\xff-declared-size"
        mismatched = self.authorize_post_image(
            "entre-token",
            "media-size-mismatch-001",
            expected_bytes,
        )
        self.assertEqual(mismatched.status_code, 201, mismatched.text)
        mismatch_authorization = mismatched.json()
        self.media_storage.simulate_signed_put(
            mismatch_authorization,
            expected_bytes + b"-unexpected",
        )
        mismatch_confirmation = self.client.post(
            f"/v1/media/uploads/{mismatch_authorization['media_id']}/confirm",
            headers=self.headers("entre-token"),
        )
        self.assertEqual(
            mismatch_confirmation.status_code,
            422,
            mismatch_confirmation.text,
        )
        self.assertEqual(
            mismatch_confirmation.json()["code"],
            "MEDIA_OBJECT_SIZE_MISMATCH",
        )
        self.assertEqual(
            self.store.get_media_asset(
                mismatch_authorization["media_id"]
            ).status,
            "rejected",
        )
        self.assertNotIn(
            mismatch_authorization["object_key"],
            self.media_storage.objects,
        )

    def test_media_confirmation_is_idempotent_after_ready(self) -> None:
        authorization, first_confirmation = self.upload_ready_post_image(
            "entre-token",
            "media-confirm-idempotent-001",
        )
        self.assertEqual(first_confirmation.json()["status"], "ready")
        self.assertEqual(self.media_storage.replace_calls, 1)

        duplicate = self.client.post(
            f"/v1/media/uploads/{authorization['media_id']}/confirm",
            headers=self.headers("entre-token"),
        )
        self.assertEqual(duplicate.status_code, 200, duplicate.text)
        self.assertEqual(duplicate.json()["status"], "ready")
        self.assertEqual(
            duplicate.json()["checksum_sha256"],
            first_confirmation.json()["checksum_sha256"],
        )
        self.assertEqual(self.media_storage.replace_calls, 1)

    def test_media_upload_denies_suspended_account_and_third_party_product(
        self,
    ) -> None:
        visitor = self.store.get_access_account("visit-uid")
        assert visitor is not None
        self.store.set_access_account(replace(visitor, status="SUSPENDED"))
        suspended = self.authorize_post_image(
            "visit-token",
            "media-suspended-001",
            b"\xff\xd8\xff-suspended",
        )
        self.assertEqual(suspended.status_code, 403, suspended.text)
        self.assertEqual(suspended.json()["code"], "ACCOUNT_SUSPENDED")

        product_id = self.prepare_product()
        third_party = self.client.post(
            "/v1/media/uploads",
            headers=self.headers("entre-other-token"),
            json={
                "entity_type": "product",
                "entity_id": product_id,
                "media_role": "product_image",
                "original_filename": "produto.png",
                "content_type": "image/png",
                "size_bytes": 2_048,
                "client_request_id": "media-product-third-party-001",
            },
        )
        self.assertEqual(third_party.status_code, 403, third_party.text)
        self.assertEqual(third_party.json()["code"], "MEDIA_ENTITY_NOT_OWNED")

    def test_public_entity_media_selects_processed_variant_in_one_lookup(
        self,
    ) -> None:
        product_id = self.prepare_product()
        raw_image = b"\x89PNG\r\n\x1a\n-product"
        authorized = self.client.post(
            "/v1/media/uploads",
            headers=self.headers("entre-token"),
            json={
                "entity_type": "product",
                "entity_id": product_id,
                "media_role": "product_image",
                "original_filename": "produto.png",
                "content_type": "image/png",
                "size_bytes": len(raw_image),
                "client_request_id": "media-product-public-001",
            },
        )
        self.assertEqual(authorized.status_code, 201, authorized.text)
        authorization = authorized.json()
        self.media_storage.simulate_signed_put(authorization, raw_image)
        processed_bytes = b"processed-product"
        processed = ProcessedImage(
            data=processed_bytes,
            content_type="image/webp",
            width=900,
            height=600,
            checksum_sha256=hashlib.sha256(processed_bytes).hexdigest(),
            variants=tuple(
                ProcessedImageVariant(
                    variant=name,
                    data=data,
                    content_type="image/webp",
                    width=width,
                    height=height,
                    checksum_sha256=hashlib.sha256(data).hexdigest(),
                )
                for name, data, width, height in (
                    ("thumbnail", b"product-thumbnail", 320, 213),
                    ("display", b"product-display", 1024, 683),
                )
            ),
        )
        with patch("trq_bec.server.service.process_image", return_value=processed):
            confirmed = self.client.post(
                f"/v1/media/uploads/{authorization['media_id']}/confirm",
                headers=self.headers("entre-token"),
            )
        self.assertEqual(confirmed.status_code, 200, confirmed.text)

        with patch.object(
            self.store,
            "get_latest_ready_media_for_entity",
            wraps=self.store.get_latest_ready_media_for_entity,
        ) as entity_lookup:
            thumbnail = self.client.get(
                f"/v1/public/media/entities/product/{product_id}/product_image",
                follow_redirects=False,
            )
        self.assertEqual(entity_lookup.call_count, 1)
        self.assertEqual(thumbnail.status_code, 307, thumbnail.text)
        self.assertIn(".thumbnail.webp", thumbnail.headers["location"])
        self.assertIn("public, max-age=60", thumbnail.headers["cache-control"])

        display = self.client.get(
            f"/v1/public/media/entities/product/{product_id}/product_image?variant=display",
            follow_redirects=False,
        )
        self.assertEqual(display.status_code, 307, display.text)
        self.assertIn(".display.webp", display.headers["location"])

        mismatched_role = self.client.get(
            f"/v1/public/media/entities/product/{product_id}/fair_cover",
            follow_redirects=False,
        )
        self.assertEqual(mismatched_role.status_code, 404, mismatched_role.text)

    def test_institution_can_upload_only_its_own_logo(self) -> None:
        own_logo = self.client.post(
            "/v1/media/uploads",
            headers=self.headers("institution-token"),
            json={
                "entity_type": "institution",
                "entity_id": "institution-uid",
                "media_role": "institution_logo",
                "original_filename": "instituicao.webp",
                "content_type": "image/webp",
                "size_bytes": 4_096,
                "client_request_id": "media-institution-logo-001",
            },
        )
        self.assertEqual(own_logo.status_code, 201, own_logo.text)
        self.assertEqual(
            self.store.get_media_asset(own_logo.json()["media_id"]).entity_id,
            "institution-uid",
        )

        another_institution = self.client.post(
            "/v1/media/uploads",
            headers=self.headers("institution-token"),
            json={
                "entity_type": "institution",
                "entity_id": "institution-other-uid",
                "media_role": "institution_logo",
                "original_filename": "outra-instituicao.webp",
                "content_type": "image/webp",
                "size_bytes": 4_096,
                "client_request_id": "media-institution-logo-002",
            },
        )
        self.assertEqual(
            another_institution.status_code,
            403,
            another_institution.text,
        )
        self.assertEqual(
            another_institution.json()["code"],
            "MEDIA_ENTITY_NOT_OWNED",
        )

    def test_support_attachment_requires_authorized_ticket(self) -> None:
        self.assertEqual(
            self.save_public_profile("visit-token", "Visitante do Suporte").status_code,
            200,
        )
        ticket = self.client.post(
            "/v1/support/requests",
            headers=self.headers("visit-token"),
            json={
                "subject": "Imagem para analise",
                "content": "Preciso encaminhar uma captura de tela.",
            },
        )
        self.assertEqual(ticket.status_code, 201, ticket.text)
        conversation_id = ticket.json()["conversation"]["conversation_id"]
        attachment_payload = {
            "entity_type": "support",
            "entity_id": conversation_id,
            "media_role": "support_attachment",
            "original_filename": "captura.png",
            "content_type": "image/png",
            "size_bytes": 2_048,
            "client_request_id": "media-support-attachment-001",
        }

        support_attachment = self.client.post(
            "/v1/media/uploads",
            headers=self.headers("support-token"),
            json=attachment_payload,
        )
        self.assertEqual(
            support_attachment.status_code,
            201,
            support_attachment.text,
        )

        unrelated_entrepreneur = self.client.post(
            "/v1/media/uploads",
            headers=self.headers("entre-token"),
            json={
                **attachment_payload,
                "client_request_id": "media-support-attachment-002",
            },
        )
        self.assertEqual(
            unrelated_entrepreneur.status_code,
            403,
            unrelated_entrepreneur.text,
        )
        self.assertEqual(
            unrelated_entrepreneur.json()["code"],
            "MEDIA_ENTITY_NOT_OWNED",
        )

        nonexistent_ticket = self.client.post(
            "/v1/media/uploads",
            headers=self.headers("support-token"),
            json={
                **attachment_payload,
                "entity_id": "CONV-NOT-FOUND",
                "client_request_id": "media-support-attachment-003",
            },
        )
        self.assertEqual(
            nonexistent_ticket.status_code,
            403,
            nonexistent_ticket.text,
        )
        self.assertEqual(
            nonexistent_ticket.json()["code"],
            "MEDIA_ENTITY_NOT_OWNED",
        )

    def test_admin_cleans_expired_pending_media_and_audits_result(self) -> None:
        authorized = self.authorize_post_image(
            "visit-token",
            "media-expired-cleanup-001",
            b"\xff\xd8\xff-expired",
        )
        self.assertEqual(authorized.status_code, 201, authorized.text)
        media_id = authorized.json()["media_id"]
        record = self.store.get_media_asset(media_id)
        assert record is not None
        self.store.media_assets[media_id] = replace(
            record,
            upload_expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )

        visitor_denied = self.client.post(
            "/v1/admin/media/cleanup",
            headers=self.headers("visit-token"),
        )
        self.assertEqual(visitor_denied.status_code, 403, visitor_denied.text)

        cleaned = self.client.post(
            "/v1/admin/media/cleanup?limit=25",
            headers=self.headers("admin-token"),
        )
        self.assertEqual(cleaned.status_code, 200, cleaned.text)
        self.assertEqual(
            cleaned.json(),
            {"scanned": 1, "cleaned": 1, "failed": 0},
        )
        self.assertEqual(self.store.get_media_asset(media_id).status, "orphaned")
        cleanup_events = [
            event
            for event in self.store.events
            if event["event_type"] == "MEDIA_ORPHAN_CLEANUP"
        ]
        self.assertEqual(len(cleanup_events), 1)
        self.assertEqual(cleanup_events[0]["result"], "CLEANED")
        self.assertEqual(cleanup_events[0]["details"]["media_id"], media_id)

    def test_media_storage_disabled_and_provider_failure_are_fail_closed(
        self,
    ) -> None:
        sentinel = "https://storage.example.test/signed?secret=DO_NOT_LEAK"
        self.media_storage.create_upload_error_code = "MEDIA_UPLOAD_URL_FAILED"
        failed = self.authorize_post_image(
            "entre-token",
            "media-storage-failure-001",
            b"\xff\xd8\xff-storage-error",
        )
        self.assertEqual(failed.status_code, 503, failed.text)
        self.assertEqual(failed.json()["code"], "MEDIA_UPLOAD_URL_FAILED")
        self.assertNotIn(sentinel, failed.text)
        failed_record = self.store.get_media_asset_by_client_request(
            "entre-uid",
            "media-storage-failure-001",
        )
        assert failed_record is not None
        self.assertEqual(failed_record.status, "rejected")

        self.service.media_storage = DisabledStorageProvider()
        disabled = self.authorize_post_image(
            "visit-token",
            "media-storage-disabled-001",
            b"\xff\xd8\xff-disabled",
        )
        self.assertEqual(disabled.status_code, 503, disabled.text)
        self.assertEqual(disabled.json()["code"], "MEDIA_STORAGE_DISABLED")
        self.assertIsNone(
            self.store.get_media_asset_by_client_request(
                "visit-uid",
                "media-storage-disabled-001",
            )
        )

    def test_admin_media_deletion_is_authorized_and_audited(self) -> None:
        authorization, _ = self.upload_ready_post_image(
            "visit-token",
            "media-admin-delete-001",
        )
        media_id = authorization["media_id"]
        deleted = self.client.delete(
            f"/v1/media/{media_id}",
            headers=self.headers("admin-token"),
        )
        self.assertEqual(deleted.status_code, 204, deleted.text)
        record = self.store.get_media_asset(media_id)
        assert record is not None
        self.assertEqual(record.status, "deleted")
        self.assertEqual(record.deleted_by, "admin-uid")
        admin_events = [
            event
            for event in self.store.events
            if event["event_type"] == "MEDIA_ADMIN_ACTION"
        ]
        self.assertEqual(len(admin_events), 1)
        self.assertEqual(admin_events[0]["result"], "DELETED")
        self.assertEqual(admin_events[0]["details"]["action"], "delete")
        self.assertEqual(admin_events[0]["details"]["previous_status"], "ready")
        self.assertEqual(admin_events[0]["details"]["new_status"], "deleted")

    def test_media_upload_rejects_path_traversal(self) -> None:
        traversal = self.client.post(
            "/v1/media/uploads",
            headers=self.headers("visit-token"),
            json={
                "entity_type": "post",
                "entity_id": None,
                "media_role": "post_image",
                "original_filename": "../foto.jpg",
                "content_type": "image/jpeg",
                "size_bytes": 1_024,
                "client_request_id": "media-path-traversal-001",
            },
        )
        self.assertEqual(traversal.status_code, 422, traversal.text)

        invalid_entity = self.client.post(
            "/v1/media/uploads",
            headers=self.headers("visit-token"),
            json={
                "entity_type": "user",
                "entity_id": "../visit-uid",
                "media_role": "avatar",
                "original_filename": "avatar.jpg",
                "content_type": "image/jpeg",
                "size_bytes": 1_024,
                "client_request_id": "media-path-traversal-002",
            },
        )
        self.assertEqual(invalid_entity.status_code, 422, invalid_entity.text)

    def test_community_posts_derive_author_and_require_current_feed_permission(self) -> None:
        payload = {
            "text": "  Publicacao compartilhada  ",
        }
        entrepreneur = self.client.post(
            "/v1/community/posts",
            headers=self.headers("entre-token"),
            json=payload,
        )
        self.assertEqual(entrepreneur.status_code, 201, entrepreneur.text)
        self.assertEqual(entrepreneur.json()["status"], "approved")
        saved = self.community.posts[entrepreneur.json()["document_id"]]
        self.assertEqual(saved["uid"], "entre-uid")
        self.assertEqual(saved["role"], "entrepreneur")
        self.assertEqual(saved["request"].text, "Publicacao compartilhada")
        self.assertIsNone(saved["request"].media)

        visitor = self.client.post(
            "/v1/community/posts",
            headers=self.headers("visit-token"),
            json={"text": "Publicacao de visitante"},
        )
        self.assertEqual(visitor.status_code, 201, visitor.text)
        visitor_saved = self.community.posts[visitor.json()["document_id"]]
        self.assertEqual(visitor_saved["uid"], "visit-uid")
        self.assertEqual(visitor_saved["role"], "visitor")

        injected_author = self.client.post(
            "/v1/community/posts",
            headers=self.headers("visit-token"),
            json={
                "text": "Tentativa de autoria falsa",
                "authorId": "admin-uid",
                "authorRole": "admin",
                "author": "Administrador",
            },
        )
        self.assertEqual(injected_author.status_code, 422, injected_author.text)

        staff = self.client.post(
            "/v1/community/posts",
            headers=self.headers("support-token"),
            json={"text": "Equipe nao publica no Feed por esta rota"},
        )
        self.assertEqual(staff.status_code, 403, staff.text)

        current_visitor = self.store.get_access_account("visit-uid")
        assert current_visitor is not None
        self.store.set_access_account(
            replace(
                current_visitor,
                permissions=tuple(
                    permission
                    for permission in current_visitor.permissions
                    if permission != "feed.publish"
                ),
            )
        )
        removed_permission = self.client.post(
            "/v1/community/posts",
            headers=self.headers("visit-token"),
            json={"text": "Sem permissao atual"},
        )
        self.assertEqual(removed_permission.status_code, 403, removed_permission.text)

        current_entrepreneur = self.store.get_access_account("entre-uid")
        assert current_entrepreneur is not None
        self.store.set_access_account(replace(current_entrepreneur, status="SUSPENDED"))
        suspended = self.client.post(
            "/v1/community/posts",
            headers=self.headers("entre-token"),
            json={"text": "Conta suspensa"},
        )
        self.assertEqual(suspended.status_code, 403, suspended.text)

    def test_merchant_approval_does_not_reactivate_or_reassign_access(self) -> None:
        disabled_uid = "disabled-merchant-uid"
        custom_permissions = ("entrepreneur.panel.access",)
        self.store.set_access_account(
            AccessAccountRecord(
                disabled_uid,
                "disabled@example.test",
                "entrepreneur",
                "DISABLED",
                False,
                custom_permissions,
            )
        )
        disabled = self.client.post(
            "/internal/v1/marketplace/merchants/status",
            headers=self.headers("admin-token"),
            json={
                "firebase_uid": disabled_uid,
                "display_name": "Conta desabilitada",
                "establishment_id": "EST-DISABLED",
                "establishment_name": "Não reativar",
                "status": "ACTIVE",
            },
        )
        self.assertEqual(disabled.status_code, 409, disabled.text)
        disabled_access = self.store.get_access_account(disabled_uid)
        assert disabled_access is not None
        self.assertEqual(disabled_access.status, "DISABLED")
        self.assertEqual(disabled_access.permissions, custom_permissions)

        support = self.client.post(
            "/internal/v1/marketplace/merchants/status",
            headers=self.headers("admin-token"),
            json={
                "firebase_uid": "support-uid",
                "display_name": "Equipe de suporte",
                "establishment_id": "EST-SUPPORT",
                "establishment_name": "Não converter função",
                "status": "ACTIVE",
            },
        )
        self.assertEqual(support.status_code, 409, support.text)
        support_access = self.store.get_access_account("support-uid")
        assert support_access is not None
        self.assertEqual(support_access.role, "support")

    def test_merchant_operation_requires_marketplace_permission(self) -> None:
        admin = self.store.get_access_account("admin-uid")
        assert admin is not None
        self.assertIn("admin.accounts.manage", admin.permissions)
        self.store.set_access_account(
            replace(
                admin,
                permissions=tuple(
                    permission
                    for permission in admin.permissions
                    if permission != "admin.marketplace.manage"
                ),
            )
        )
        denied = self.client.post(
            "/internal/v1/marketplace/merchants/status",
            headers=self.headers("admin-token"),
            json={
                "firebase_uid": "entre-uid",
                "display_name": "Empreendedor",
                "establishment_id": "EST-PERMISSION",
                "establishment_name": "Operacao sem permissao",
                "status": "ACTIVE",
            },
        )
        self.assertEqual(denied.status_code, 403, denied.text)
        self.assertEqual(denied.json()["code"], "ACCOUNT_PERMISSION_REQUIRED")

    def prepare_product(self, *, price_minor: int = 5_000, stock_quantity: int = 10) -> str:
        approved = self.client.post(
            "/internal/v1/marketplace/merchants/status",
            headers=self.headers("admin-token"),
            json={
                "firebase_uid": "entre-uid",
                "display_name": "Artesã da Feira",
                "establishment_id": "EST-FEIRA-TESTE",
                "establishment_name": "Feira LiberRotas",
                "status": "ACTIVE",
            },
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        created = self.client.post(
            "/v1/marketplace/products",
            headers=self.headers("entre-token"),
            json={
                "title": "Bordado artesanal",
                "description": "Produto de teste",
                "price_minor": price_minor,
                "currency": "BRL",
                "stock_quantity": stock_quantity,
            },
        )
        self.assertEqual(created.status_code, 200, created.text)
        return created.json()["product_id"]

    def issue_offer(
        self,
        product_id: str,
        *,
        maximum_redemptions: int = 2,
        discount_type: str = "PERCENT",
        discount_value: int = 20,
        validity_minutes: int = 5,
    ):
        current_device = self.store.devices.get("device:entre-test")
        if current_device is not None and current_device.status == "PENDING_APPROVAL":
            self.store.devices["device:entre-test"] = replace(
                current_device,
                approval_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
            )
            activated = self.client.get(
                "/v1/account/devices",
                headers=self.headers("entre-token"),
            )
            self.assertEqual(activated.status_code, 200, activated.text)
        return self.client.post(
            "/v1/trq-bec/coupons/issue",
            headers=self.headers("entre-token"),
            json={
                "product_id": product_id,
                "discount_type": discount_type,
                "discount_value": discount_value,
                "maximum_redemptions": maximum_redemptions,
                "valid_until": (
                    datetime.now(timezone.utc) + timedelta(minutes=validity_minutes)
                ).isoformat(),
                "purpose": "LIVE_FAIR_DISCOUNT",
                "device_key_id": "device:entre-test",
            },
        )

    def test_product_batch_archive_is_atomic_and_revokes_linked_offers(self) -> None:
        self.assertEqual(
            self.enroll("entre-token", "device:entre-test", self.entre_key).status_code,
            200,
        )
        product_ids = [self.prepare_product(), self.prepare_product()]
        issued = [self.issue_offer(product_id) for product_id in product_ids]
        for response in issued:
            self.assertEqual(response.status_code, 200, response.text)
        offer_ids = [response.json()["offer_id"] for response in issued]
        token_refs = [response.json()["qr_payload"]["token_ref"] for response in issued]

        archive_request = {
            "client_request_id": "product-archive-success-001",
            "product_ids": product_ids,
        }
        events_before_archive = len(self.store.events)
        archived = self.client.post(
            "/v1/marketplace/products/batch/archive",
            headers=self.headers("entre-token"),
            json=archive_request,
        )
        self.assertEqual(archived.status_code, 200, archived.text)
        self.assertTrue(archived.json()["operation_id"].startswith("product-batch:"))
        self.assertEqual(archived.json()["archived_count"], 2)
        self.assertEqual(
            [item["product_id"] for item in archived.json()["products"]],
            product_ids,
        )
        self.assertTrue(
            all(item["status"] == "ARCHIVED" for item in archived.json()["products"])
        )
        self.assertTrue(
            all(self.store.offers[offer_id].status == "REVOKED" for offer_id in offer_ids)
        )
        self.assertTrue(
            all(self.store.tokens[token_ref].status == "REVOKED" for token_ref in token_refs)
        )
        catalog_ids = {
            item.product_id for item in self.store.list_public_catalog(limit=50)
        }
        self.assertTrue(set(product_ids).isdisjoint(catalog_ids))
        managed = self.client.get(
            "/v1/marketplace/products/mine",
            headers=self.headers("entre-token"),
        )
        self.assertEqual(managed.status_code, 200, managed.text)
        managed_ids = {item["product_id"] for item in managed.json()["products"]}
        self.assertTrue(set(product_ids).isdisjoint(managed_ids))
        events_after_archive = len(self.store.events)
        self.assertEqual(events_after_archive, events_before_archive + 1)

        repeated_archive = self.client.post(
            "/v1/marketplace/products/batch/archive",
            headers=self.headers("entre-token"),
            json=archive_request,
        )
        self.assertEqual(repeated_archive.status_code, 200, repeated_archive.text)
        self.assertEqual(repeated_archive.json(), archived.json())
        self.assertEqual(len(self.store.events), events_after_archive)

        active_product = self.prepare_product()
        reused_request_id = self.client.post(
            "/v1/marketplace/products/batch/archive",
            headers=self.headers("entre-token"),
            json={
                "client_request_id": "product-archive-success-001",
                "product_ids": [active_product],
            },
        )
        self.assertEqual(reused_request_id.status_code, 409, reused_request_id.text)
        self.assertEqual(
            reused_request_id.json()["code"], "BATCH_CLIENT_REQUEST_ID_REUSED"
        )
        self.assertEqual(self.store.products[active_product].status, "ACTIVE")

        failed = self.client.post(
            "/v1/marketplace/products/batch/archive",
            headers=self.headers("entre-token"),
            json={
                "client_request_id": "product-archive-missing-001",
                "product_ids": [active_product, "PROD-AAAAAAAA"],
            },
        )
        self.assertEqual(failed.status_code, 404, failed.text)
        self.assertEqual(self.store.products[active_product].status, "ACTIVE")

        foreign_product_id = "PROD-BBBBBBBB"
        self.store.products[foreign_product_id] = replace(
            self.store.products[active_product],
            product_id=foreign_product_id,
            merchant_uid="another-merchant-uid",
        )
        foreign_owner = self.client.post(
            "/v1/marketplace/products/batch/archive",
            headers=self.headers("entre-token"),
            json={
                "client_request_id": "product-archive-foreign-001",
                "product_ids": [active_product, foreign_product_id],
            },
        )
        self.assertEqual(foreign_owner.status_code, 404, foreign_owner.text)
        self.assertEqual(self.store.products[active_product].status, "ACTIVE")

        duplicate = self.client.post(
            "/v1/marketplace/products/batch/archive",
            headers=self.headers("entre-token"),
            json={
                "client_request_id": "product-archive-duplicate-001",
                "product_ids": [active_product, active_product],
            },
        )
        self.assertEqual(duplicate.status_code, 422, duplicate.text)

        mixed_active_product = self.prepare_product()
        mixed_archive = self.client.post(
            "/v1/marketplace/products/batch/archive",
            headers=self.headers("entre-token"),
            json={
                "client_request_id": "product-archive-mixed-001",
                "product_ids": [product_ids[0], product_ids[1], mixed_active_product],
            },
        )
        self.assertEqual(mixed_archive.status_code, 200, mixed_archive.text)
        self.assertEqual(mixed_archive.json()["archived_count"], 3)
        self.assertTrue(
            all(
                self.store.products[product_id].status == "ARCHIVED"
                for product_id in [product_ids[0], product_ids[1], mixed_active_product]
            )
        )

    def test_product_batch_activate_updates_existing_products_but_not_deleted_ones(self) -> None:
        product_ids = [self.prepare_product(stock_quantity=0), self.prepare_product(stock_quantity=2)]
        self.store.products[product_ids[0]] = replace(
            self.store.products[product_ids[0]],
            status="PAUSED",
        )
        activate_request = {
            "client_request_id": "product-activate-success-001",
            "items": [
                {"product_id": product_ids[0], "stock_quantity": 100},
                {"product_id": product_ids[1], "stock_quantity": 50},
            ],
        }
        events_before_activation = len(self.store.events)
        activated = self.client.post(
            "/v1/marketplace/products/batch/activate",
            headers=self.headers("entre-token"),
            json=activate_request,
        )
        self.assertEqual(activated.status_code, 200, activated.text)
        self.assertTrue(
            activated.json()["operation_id"].startswith("product-activate-batch:")
        )
        self.assertEqual(activated.json()["activated_count"], 2)
        self.assertEqual(
            [item["stock_quantity"] for item in activated.json()["products"]],
            [100, 50],
        )
        self.assertTrue(
            all(item["status"] == "ACTIVE" for item in activated.json()["products"])
        )
        catalog_ids = {
            item.product_id for item in self.store.list_public_catalog(limit=50)
        }
        self.assertTrue(set(product_ids).issubset(catalog_ids))
        events_after_activation = len(self.store.events)
        self.assertEqual(events_after_activation, events_before_activation + 1)

        repeated = self.client.post(
            "/v1/marketplace/products/batch/activate",
            headers=self.headers("entre-token"),
            json=activate_request,
        )
        self.assertEqual(repeated.status_code, 200, repeated.text)
        self.assertEqual(repeated.json(), activated.json())
        self.assertEqual(len(self.store.events), events_after_activation)

        deleted = self.client.post(
            "/v1/marketplace/products/batch/archive",
            headers=self.headers("entre-token"),
            json={
                "client_request_id": "product-delete-before-reactivate-001",
                "product_ids": [product_ids[0]],
            },
        )
        self.assertEqual(deleted.status_code, 200, deleted.text)
        reactivate_deleted = self.client.post(
            "/v1/marketplace/products/batch/activate",
            headers=self.headers("entre-token"),
            json={
                "client_request_id": "product-reactivate-deleted-001",
                "items": [
                    {"product_id": product_ids[0], "stock_quantity": 10},
                ],
            },
        )
        self.assertEqual(reactivate_deleted.status_code, 404, reactivate_deleted.text)

        failed = self.client.post(
            "/v1/marketplace/products/batch/activate",
            headers=self.headers("entre-token"),
            json={
                "client_request_id": "product-activate-missing-001",
                "items": [
                    {"product_id": product_ids[1], "stock_quantity": 10},
                    {"product_id": "PROD-AAAAAAAA", "stock_quantity": 10},
                ],
            },
        )
        self.assertEqual(failed.status_code, 404, failed.text)
        self.assertEqual(self.store.products[product_ids[1]].stock_quantity, 50)

        duplicate = self.client.post(
            "/v1/marketplace/products/batch/activate",
            headers=self.headers("entre-token"),
            json={
                "client_request_id": "product-activate-duplicate-001",
                "items": [
                    {"product_id": product_ids[1], "stock_quantity": 10},
                    {"product_id": product_ids[1], "stock_quantity": 20},
                ],
            },
        )
        self.assertEqual(duplicate.status_code, 422, duplicate.text)

        zero_stock = self.client.post(
            "/v1/marketplace/products/batch/activate",
            headers=self.headers("entre-token"),
            json={
                "client_request_id": "product-activate-zero-001",
                "items": [
                    {"product_id": product_ids[1], "stock_quantity": 0},
                ],
            },
        )
        self.assertEqual(zero_stock.status_code, 422, zero_stock.text)

    def test_offer_batch_rotates_qr_preserves_offer_and_deletes_with_revoke(self) -> None:
        self.assertEqual(
            self.enroll("entre-token", "device:entre-test", self.entre_key).status_code,
            200,
        )
        product_ids = [self.prepare_product(), self.prepare_product()]
        issued = [self.issue_offer(product_id) for product_id in product_ids]
        for response in issued:
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["offer"]["discount_type"], "PERCENT")
            self.assertEqual(response.json()["offer"]["discount_value"], 20)
        offer_ids = [response.json()["offer_id"] for response in issued]
        self.store.offers[offer_ids[0]] = replace(
            self.store.offers[offer_ids[0]], redeemed_count=1
        )
        original_token_refs = [
            response.json()["qr_payload"]["token_ref"] for response in issued
        ]
        original_expiries = [response.json()["offer"]["expires_at"] for response in issued]

        increase_request = {
            "client_request_id": "offer-increase-success-001",
            "action": "INCREASE_DISCOUNT",
            "offer_ids": offer_ids,
            "discount_type": "PERCENT",
            "discount_delta": 5,
            "device_key_id": "device:entre-test",
        }
        events_before_increase = len(self.store.events)
        increased = self.client.post(
            "/v1/marketplace/offers/batch/actions",
            headers=self.headers("entre-token"),
            json=increase_request,
        )
        self.assertEqual(increased.status_code, 200, increased.text)
        increased_body = increased.json()
        self.assertTrue(increased_body["operation_id"].startswith("offer-batch:"))
        self.assertEqual(increased_body["action"], "INCREASE_DISCOUNT")
        self.assertEqual(increased_body["updated_count"], 2)
        self.assertEqual(
            [item["offer"]["offer_id"] for item in increased_body["items"]],
            offer_ids,
        )
        self.assertTrue(
            all(item["offer"]["discount_value"] == 25 for item in increased_body["items"])
        )
        self.assertEqual(
            [item["offer"]["expires_at"] for item in increased_body["items"]],
            original_expiries,
        )
        increased_token_refs = [
            item["qr_payload"]["token_ref"] for item in increased_body["items"]
        ]
        self.assertTrue(
            all(self.store.tokens[token_ref].status == "REVOKED" for token_ref in original_token_refs)
        )
        self.assertTrue(
            all(self.store.tokens[token_ref].status == "ISSUED" for token_ref in increased_token_refs)
        )
        self.assertEqual(
            [self.store.offers[offer_id].redeemed_count for offer_id in offer_ids],
            [1, 0],
        )
        events_after_increase = len(self.store.events)
        self.assertEqual(events_after_increase, events_before_increase + 1)

        repeated_increase = self.client.post(
            "/v1/marketplace/offers/batch/actions",
            headers=self.headers("entre-token"),
            json=increase_request,
        )
        self.assertEqual(repeated_increase.status_code, 200, repeated_increase.text)
        self.assertEqual(repeated_increase.json(), increased_body)
        self.assertEqual(
            [self.store.offers[offer_id].token_ref for offer_id in offer_ids],
            increased_token_refs,
        )
        self.assertEqual(
            [self.store.offers[offer_id].discount_value for offer_id in offer_ids],
            [25, 25],
        )
        self.assertEqual(len(self.store.events), events_after_increase)

        changed_increase = self.client.post(
            "/v1/marketplace/offers/batch/actions",
            headers=self.headers("entre-token"),
            json={**increase_request, "discount_delta": 6},
        )
        self.assertEqual(changed_increase.status_code, 409, changed_increase.text)
        self.assertEqual(
            changed_increase.json()["code"], "BATCH_CLIENT_REQUEST_ID_REUSED"
        )

        extend_request = {
            "client_request_id": "offer-extend-success-001",
            "action": "EXTEND_VALIDITY",
            "offer_ids": offer_ids,
            "extension_minutes": 60,
            "device_key_id": "device:entre-test",
        }
        extended = self.client.post(
            "/v1/marketplace/offers/batch/actions",
            headers=self.headers("entre-token"),
            json=extend_request,
        )
        self.assertEqual(extended.status_code, 200, extended.text)
        extended_body = extended.json()
        self.assertEqual(extended_body["action"], "EXTEND_VALIDITY")
        self.assertEqual(
            [item["offer"]["expires_at"] for item in extended_body["items"]],
            [expires_at + 3600 for expires_at in original_expiries],
        )
        extended_token_refs = [
            item["qr_payload"]["token_ref"] for item in extended_body["items"]
        ]
        self.assertTrue(
            all(self.store.tokens[token_ref].status == "REVOKED" for token_ref in increased_token_refs)
        )
        self.assertTrue(
            all(self.store.tokens[token_ref].status == "ISSUED" for token_ref in extended_token_refs)
        )
        repeated_extend = self.client.post(
            "/v1/marketplace/offers/batch/actions",
            headers=self.headers("entre-token"),
            json=extend_request,
        )
        self.assertEqual(repeated_extend.status_code, 200, repeated_extend.text)
        self.assertEqual(repeated_extend.json(), extended_body)
        self.assertEqual(
            [self.store.offers[offer_id].token_ref for offer_id in offer_ids],
            extended_token_refs,
        )

        delete_request = {
            "client_request_id": "offer-delete-success-001",
            "action": "DELETE",
            "offer_ids": offer_ids,
        }
        deleted = self.client.post(
            "/v1/marketplace/offers/batch/actions",
            headers=self.headers("entre-token"),
            json=delete_request,
        )
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertEqual(deleted.json()["action"], "DELETE")
        self.assertEqual(deleted.json()["updated_count"], 2)
        self.assertTrue(
            all(item["qr_payload"] is None for item in deleted.json()["items"])
        )
        self.assertTrue(
            all(item["offer"]["status"] == "REVOKED" for item in deleted.json()["items"])
        )
        self.assertTrue(
            all(
                item["offer"]["remaining_redemptions"] == 0
                for item in deleted.json()["items"]
            )
        )
        self.assertTrue(
            all(self.store.tokens[token_ref].status == "REVOKED" for token_ref in extended_token_refs)
        )
        public_offers = {
            offer.offer_id
            for product in self.store.list_public_catalog(limit=50)
            for offer in product.offers
        }
        self.assertTrue(set(offer_ids).isdisjoint(public_offers))
        repeated_delete = self.client.post(
            "/v1/marketplace/offers/batch/actions",
            headers=self.headers("entre-token"),
            json=delete_request,
        )
        self.assertEqual(repeated_delete.status_code, 200, repeated_delete.text)
        self.assertEqual(repeated_delete.json(), deleted.json())

    def test_offer_batch_rejects_invalid_or_final_selection_without_partial_write(self) -> None:
        self.assertEqual(
            self.enroll("entre-token", "device:entre-test", self.entre_key).status_code,
            200,
        )
        product_ids = [self.prepare_product(), self.prepare_product()]
        issued = [
            self.issue_offer(product_ids[0], discount_value=85),
            self.issue_offer(product_ids[1], discount_value=20),
        ]
        for response in issued:
            self.assertEqual(response.status_code, 200, response.text)
        offer_ids = [response.json()["offer_id"] for response in issued]
        token_refs_before = [self.store.offers[offer_id].token_ref for offer_id in offer_ids]

        over_limit = self.client.post(
            "/v1/marketplace/offers/batch/actions",
            headers=self.headers("entre-token"),
            json={
                "client_request_id": "offer-increase-limit-001",
                "action": "INCREASE_DISCOUNT",
                "offer_ids": offer_ids,
                "discount_type": "PERCENT",
                "discount_delta": 10,
                "device_key_id": "device:entre-test",
            },
        )
        self.assertEqual(over_limit.status_code, 400, over_limit.text)
        self.assertEqual(over_limit.json()["code"], "OFFER_BATCH_DISCOUNT_LIMIT_EXCEEDED")
        self.assertEqual(
            [self.store.offers[offer_id].token_ref for offer_id in offer_ids],
            token_refs_before,
        )
        self.assertEqual(
            [self.store.offers[offer_id].discount_value for offer_id in offer_ids],
            [85, 20],
        )

        unknown_device = self.client.post(
            "/v1/marketplace/offers/batch/actions",
            headers=self.headers("entre-token"),
            json={
                "client_request_id": "offer-unknown-device-001",
                "action": "EXTEND_VALIDITY",
                "offer_ids": offer_ids,
                "extension_minutes": 10,
                "device_key_id": "device:unknown-test",
            },
        )
        self.assertEqual(unknown_device.status_code, 403, unknown_device.text)
        self.assertEqual(unknown_device.json()["code"], "DEVICE_NOT_ENROLLED")

        foreign_offer_id = "OFFER-BBBBBBBBBBBB"
        foreign_token_ref = "foreign-token-reference-123456789"
        source_offer = self.store.offers[offer_ids[1]]
        source_token = self.store.tokens[source_offer.token_ref]
        self.store.offers[foreign_offer_id] = replace(
            source_offer,
            offer_id=foreign_offer_id,
            token_ref=foreign_token_ref,
            merchant_uid="another-merchant-uid",
        )
        self.store.tokens[foreign_token_ref] = replace(
            source_token,
            token_ref=foreign_token_ref,
            offer_id=foreign_offer_id,
            issuer_uid="another-merchant-uid",
        )
        active_before_foreign_check = self.store.offers[offer_ids[1]]
        foreign_owner = self.client.post(
            "/v1/marketplace/offers/batch/actions",
            headers=self.headers("entre-token"),
            json={
                "client_request_id": "offer-delete-foreign-001",
                "action": "DELETE",
                "offer_ids": [offer_ids[1], foreign_offer_id],
            },
        )
        self.assertEqual(foreign_owner.status_code, 404, foreign_owner.text)
        self.assertEqual(
            self.store.offers[offer_ids[1]], active_before_foreign_check
        )

        cancelled = self.client.post(
            f"/v1/marketplace/offers/{offer_ids[0]}/status",
            headers=self.headers("entre-token"),
            json={"status": "CANCELLED"},
        )
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        active_before = self.store.offers[offer_ids[1]]
        final_selection = self.client.post(
            "/v1/marketplace/offers/batch/actions",
            headers=self.headers("entre-token"),
            json={
                "client_request_id": "offer-delete-final-001",
                "action": "DELETE",
                "offer_ids": offer_ids,
            },
        )
        self.assertEqual(final_selection.status_code, 404, final_selection.text)
        self.assertEqual(self.store.offers[offer_ids[1]], active_before)

        duplicate = self.client.post(
            "/v1/marketplace/offers/batch/actions",
            headers=self.headers("entre-token"),
            json={
                "client_request_id": "offer-delete-duplicate-001",
                "action": "DELETE",
                "offer_ids": [offer_ids[1], offer_ids[1]],
            },
        )
        self.assertEqual(duplicate.status_code, 422, duplicate.text)

    def test_offer_batch_validates_type_token_and_maximum_ttl_before_rotation(self) -> None:
        self.assertEqual(
            self.enroll("entre-token", "device:entre-test", self.entre_key).status_code,
            200,
        )
        percent_product = self.prepare_product()
        fixed_product = self.prepare_product()
        percent_issue = self.issue_offer(
            percent_product,
            discount_value=20,
            validity_minutes=180,
        )
        fixed_issue = self.issue_offer(
            fixed_product,
            discount_type="FIXED_AMOUNT",
            discount_value=500,
            validity_minutes=180,
        )
        self.assertEqual(percent_issue.status_code, 200, percent_issue.text)
        self.assertEqual(fixed_issue.status_code, 200, fixed_issue.text)
        offer_ids = [percent_issue.json()["offer_id"], fixed_issue.json()["offer_id"]]
        original_tokens = [self.store.offers[item].token_ref for item in offer_ids]

        mixed = self.client.post(
            "/v1/marketplace/offers/batch/actions",
            headers=self.headers("entre-token"),
            json={
                "client_request_id": "offer-increase-mixed-001",
                "action": "INCREASE_DISCOUNT",
                "offer_ids": offer_ids,
                "discount_type": "PERCENT",
                "discount_delta": 5,
                "device_key_id": "device:entre-test",
            },
        )
        self.assertEqual(mixed.status_code, 409, mixed.text)
        self.assertEqual(mixed.json()["code"], "OFFER_BATCH_DISCOUNT_TYPE_MISMATCH")
        self.assertEqual(
            [self.store.offers[item].token_ref for item in offer_ids],
            original_tokens,
        )

        too_long = self.client.post(
            "/v1/marketplace/offers/batch/actions",
            headers=self.headers("entre-token"),
            json={
                "client_request_id": "offer-extend-too-long-001",
                "action": "EXTEND_VALIDITY",
                "offer_ids": offer_ids,
                "extension_minutes": 360,
                "device_key_id": "device:entre-test",
            },
        )
        self.assertEqual(too_long.status_code, 400, too_long.text)
        self.assertEqual(too_long.json()["code"], "OFFER_VALIDITY_TOO_LONG")
        self.assertEqual(
            [self.store.offers[item].token_ref for item in offer_ids],
            original_tokens,
        )

        invalid_token = self.store.tokens[original_tokens[0]]
        self.store.tokens[original_tokens[0]] = replace(
            invalid_token, status="REVOKED"
        )
        token_rejected = self.client.post(
            "/v1/marketplace/offers/batch/actions",
            headers=self.headers("entre-token"),
            json={
                "client_request_id": "offer-delete-token-invalid-001",
                "action": "DELETE",
                "offer_ids": offer_ids,
            },
        )
        self.assertEqual(token_rejected.status_code, 404, token_rejected.text)
        self.assertEqual(self.store.offers[offer_ids[1]].status, "ACTIVE")
        self.store.tokens[original_tokens[0]] = invalid_token

        fixed_increased = self.client.post(
            "/v1/marketplace/offers/batch/actions",
            headers=self.headers("entre-token"),
            json={
                "client_request_id": "offer-fixed-increase-001",
                "action": "INCREASE_DISCOUNT",
                "offer_ids": [offer_ids[1]],
                "discount_type": "FIXED_AMOUNT",
                "discount_delta": 250,
                "device_key_id": "device:entre-test",
            },
        )
        self.assertEqual(fixed_increased.status_code, 200, fixed_increased.text)
        fixed_offer = fixed_increased.json()["items"][0]["offer"]
        self.assertEqual(fixed_offer["discount_type"], "FIXED_AMOUNT")
        self.assertEqual(fixed_offer["discount_value"], 750)
        self.assertEqual(fixed_offer["discount_amount_minor"], 750)

    def full_flow(self):
        self.assertEqual(self.enroll("entre-token", "device:entre-test", self.entre_key).status_code, 200)
        self.assertEqual(self.enroll("visit-token", "device:visit-test", self.visit_key).status_code, 200)
        product_id = self.prepare_product()
        issued = self.issue_offer(product_id)
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

    def test_account_deletion_closes_commercial_data_before_firestore_cleanup(self) -> None:
        self.assertEqual(self.enroll("entre-token", "device:entre-test", self.entre_key).status_code, 200)
        product_id = self.prepare_product(stock_quantity=4)
        issued = self.issue_offer(product_id, maximum_redemptions=2)
        self.assertEqual(issued.status_code, 200, issued.text)
        offer_id = issued.json()["offer_id"]
        token_ref = self.store.offers[offer_id].token_ref

        response = self.client.delete(
            "/v1/account",
            headers=self.headers("entre-token"),
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.json(),
            {
                "status": "READY_FOR_AUTH_DELETION",
                "firestore_documents_deleted": 7,
                "commercial_data_disabled": True,
                "security_records_retained": True,
            },
        )
        self.assertEqual(self.cleaned_account_uids, ["entre-uid"])
        self.assertEqual(self.store.merchants["entre-uid"].status, "SUSPENDED")
        self.assertEqual(self.store.products[product_id].status, "ARCHIVED")
        self.assertEqual(self.store.offers[offer_id].status, "CANCELLED")
        self.assertEqual(self.store.tokens[token_ref].status, "REVOKED")
        self.assertEqual(self.store.devices["device:entre-test"].status, "REVOKED")
        closure_events = [event for event in self.store.events if event["event_type"] == "ACCOUNT_CLOSURE"]
        self.assertEqual(len(closure_events), 1)
        self.assertNotIn("entre-uid", str(closure_events[0]["details"]))

        catalog = self.client.get(
            "/v1/marketplace/catalog/feed",
            headers=self.headers("visit-token"),
        )
        self.assertEqual(catalog.status_code, 200, catalog.text)
        self.assertEqual(catalog.json()["items"], [])

        # A preparação pode ser repetida quando a limpeza do Firestore tiver
        # sido concluída, sem criar outro evento comercial.
        retry = self.client.delete("/v1/account", headers=self.headers("entre-token"))
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(len([event for event in self.store.events if event["event_type"] == "ACCOUNT_CLOSURE"]), 1)

    def test_account_deletion_requires_bearer_and_recent_authentication(self) -> None:
        missing = self.client.delete("/v1/account")
        stale = self.client.delete("/v1/account", headers=self.headers("stale-token"))

        self.assertEqual(missing.status_code, 401)
        self.assertEqual(missing.json()["code"], "AUTH_BEARER_REQUIRED")
        self.assertEqual(stale.status_code, 403)
        self.assertEqual(stale.json()["code"], "RECENT_AUTHENTICATION_REQUIRED")
        self.assertEqual(self.cleaned_account_uids, [])

    def test_account_deletion_preserves_login_step_when_firestore_cleanup_fails(self) -> None:
        self.prepare_product()

        def fail_cleanup(_: str) -> int:
            raise RuntimeError("firestore unavailable")

        self.client.app.state.account_cleanup = fail_cleanup
        failed = self.client.delete("/v1/account", headers=self.headers("entre-token"))

        self.assertEqual(failed.status_code, 503, failed.text)
        self.assertEqual(failed.json()["code"], "ACCOUNT_FIRESTORE_CLEANUP_FAILED")
        self.assertEqual(self.store.merchants["entre-uid"].status, "SUSPENDED")

        self.client.app.state.account_cleanup = lambda uid: self.cleaned_account_uids.append(uid) or 3
        retry = self.client.delete("/v1/account", headers=self.headers("entre-token"))
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(retry.json()["firestore_documents_deleted"], 3)
        self.assertEqual(self.cleaned_account_uids, ["entre-uid"])

    def test_issue_and_redeem_coupon(self) -> None:
        qr, request, authorized = self.full_flow()
        self.assertEqual(authorized.status_code, 200, authorized.text)
        result = authorized.json()
        self.assertEqual(result["decision"], "ALLOW")
        self.assertTrue(result["crypto_ok"])
        self.assertEqual(result["coupon_id"], result["offer_id"])
        self.assertEqual(result["product_id"], self.store.products[result["product_id"]].product_id)
        self.assertEqual(result["amount_saved_minor"], 1_000)
        self.assertEqual(result["final_amount_minor"], 4_000)
        self.assertTrue(result["event_ref"].startswith("event:"))
        second = self.client.post(
            "/v1/trq-bec/coupons/redeem/authorize",
            headers=self.headers("visit-token"),
            json=request,
        )
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json()["idempotent"])
        repeated_begin = self.client.post(
            "/v1/trq-bec/coupons/redeem/begin",
            headers=self.headers("visit-token"),
            json={"qr_payload": qr, "device_key_id": "device:visit-test"},
        )
        self.assertEqual(repeated_begin.status_code, 200)
        begin = repeated_begin.json()
        proof_message = base64.urlsafe_b64decode(
            begin["proof_message_b64u"] + "=" * (-len(begin["proof_message_b64u"]) % 4)
        )
        duplicate = self.client.post(
            "/v1/trq-bec/coupons/redeem/authorize",
            headers=self.headers("visit-token"),
            json={
                "operation_id": begin["operation_id"],
                "session_id": begin["session_id"],
                "challenge_id": begin["challenge"]["challenge_id"],
                "device_key_id": "device:visit-test",
                "device_proof_b64u": b64u(self.visit_key.sign(proof_message)),
            },
        )
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(duplicate.json()["decision"], "DENY")
        self.assertIn("OFFER_ALREADY_REDEEMED_BY_USER", duplicate.json()["reason_codes"])

    def test_same_qr_sale_can_count_two_distinct_coupons_with_equal_savings(self) -> None:
        self.assertEqual(
            self.enroll("entre-token", "device:entre-test", self.entre_key).status_code,
            200,
        )
        self.assertEqual(
            self.enroll("visit-token", "device:visit-test", self.visit_key).status_code,
            200,
        )
        first_product_id = self.prepare_product(price_minor=10_000, stock_quantity=3)
        second_product_id = self.prepare_product(price_minor=5_000, stock_quantity=3)
        first_issued = self.issue_offer(
            first_product_id,
            maximum_redemptions=3,
            discount_value=10,
        )
        second_issued = self.issue_offer(
            second_product_id,
            maximum_redemptions=3,
            discount_value=20,
        )
        self.assertEqual(first_issued.status_code, 200, first_issued.text)
        self.assertEqual(second_issued.status_code, 200, second_issued.text)

        def redeem(qr_payload: dict[str, object]):
            begun = self.client.post(
                "/v1/trq-bec/coupons/redeem/begin",
                headers=self.headers("visit-token"),
                json={"qr_payload": qr_payload, "device_key_id": "device:visit-test"},
            )
            self.assertEqual(begun.status_code, 200, begun.text)
            begin = begun.json()
            proof_message = base64.urlsafe_b64decode(
                begin["proof_message_b64u"]
                + "=" * (-len(begin["proof_message_b64u"]) % 4)
            )
            return self.client.post(
                "/v1/trq-bec/coupons/redeem/authorize",
                headers=self.headers("visit-token"),
                json={
                    "operation_id": begin["operation_id"],
                    "session_id": begin["session_id"],
                    "challenge_id": begin["challenge"]["challenge_id"],
                    "device_key_id": "device:visit-test",
                    "device_proof_b64u": b64u(self.visit_key.sign(proof_message)),
                },
            )

        first_authorized = redeem(first_issued.json()["qr_payload"])
        second_authorized = redeem(second_issued.json()["qr_payload"])
        self.assertEqual(first_authorized.status_code, 200, first_authorized.text)
        self.assertEqual(second_authorized.status_code, 200, second_authorized.text)
        first_result = first_authorized.json()
        second_result = second_authorized.json()
        self.assertEqual(first_result["decision"], "ALLOW")
        self.assertEqual(second_result["decision"], "ALLOW")
        self.assertEqual(first_result["amount_saved_minor"], 1_000)
        self.assertEqual(second_result["amount_saved_minor"], 1_000)

        first_offer_id = first_issued.json()["offer_id"]
        second_offer_id = second_issued.json()["offer_id"]
        self.assertNotEqual(first_offer_id, second_offer_id)
        self.assertEqual(self.store.offers[first_offer_id].redeemed_count, 1)
        self.assertEqual(self.store.offers[second_offer_id].redeemed_count, 1)
        self.assertEqual(self.store.products[first_product_id].stock_quantity, 2)
        self.assertEqual(self.store.products[second_product_id].stock_quantity, 2)
        self.assertIn((first_offer_id, "visit-uid"), self.store.redemptions)
        self.assertIn((second_offer_id, "visit-uid"), self.store.redemptions)
        self.assertEqual(
            len([
                redemption
                for redemption in self.store.redemptions.values()
                if redemption["offer_id"] in {first_offer_id, second_offer_id}
            ]),
            2,
        )
        reopened_qr = self.client.get(
            f"/v1/marketplace/offers/{first_offer_id}/qr",
            headers=self.headers("entre-token"),
        )
        self.assertEqual(reopened_qr.status_code, 200, reopened_qr.text)
        self.assertEqual(
            reopened_qr.json()["qr_payload"]["token_ref"],
            first_issued.json()["qr_payload"]["token_ref"],
        )
        self.assertEqual(reopened_qr.json()["qr_payload"]["quantity"], 1)
        self.assertRegex(
            reopened_qr.json()["qr_payload"]["quantity_proof_b64u"],
            r"^[A-Za-z0-9_-]{86}$",
        )
        self.assertEqual(reopened_qr.json()["offer"]["redeemed_count"], 1)
        self.assertEqual(reopened_qr.json()["offer"]["remaining_redemptions"], 2)

    def test_seller_signed_qr_quantity_decrements_units_atomically(self) -> None:
        self.assertEqual(
            self.enroll("entre-token", "device:entre-test", self.entre_key).status_code,
            200,
        )
        self.assertEqual(
            self.enroll("visit-token", "device:visit-test", self.visit_key).status_code,
            200,
        )
        product_id = self.prepare_product(price_minor=5_000, stock_quantity=10)
        issued = self.issue_offer(product_id, maximum_redemptions=8, discount_value=20)
        self.assertEqual(issued.status_code, 200, issued.text)
        offer_id = issued.json()["offer_id"]

        generated = self.client.get(
            f"/v1/marketplace/offers/{offer_id}/qr?quantity=3",
            headers=self.headers("entre-token"),
        )
        self.assertEqual(generated.status_code, 200, generated.text)
        generated_body = generated.json()
        qr_payload = generated_body["qr_payload"]
        self.assertEqual(qr_payload["quantity"], 3)
        self.assertRegex(qr_payload["quantity_proof_b64u"], r"^[A-Za-z0-9_-]{86}$")
        self.assertEqual(generated_body["offer"]["purchase_quantity"], 3)

        tampered_payload = {**qr_payload, "quantity": 4}
        tampered = self.client.post(
            "/v1/trq-bec/coupons/preview",
            headers=self.headers("visit-token"),
            json={"qr_payload": tampered_payload},
        )
        self.assertEqual(tampered.status_code, 400, tampered.text)
        self.assertEqual(tampered.json()["code"], "QR_QUANTITY_BINDING_INVALID")

        preview = self.client.post(
            "/v1/trq-bec/coupons/preview",
            headers=self.headers("visit-token"),
            json={"qr_payload": qr_payload},
        )
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertEqual(preview.json()["purchase_quantity"], 3)

        begun = self.client.post(
            "/v1/trq-bec/coupons/redeem/begin",
            headers=self.headers("visit-token"),
            json={"qr_payload": qr_payload, "device_key_id": "device:visit-test"},
        )
        self.assertEqual(begun.status_code, 200, begun.text)
        begin = begun.json()
        self.assertEqual(begin["offer"]["purchase_quantity"], 3)
        proof_message = base64.urlsafe_b64decode(
            begin["proof_message_b64u"]
            + "=" * (-len(begin["proof_message_b64u"]) % 4)
        )
        authorized = self.client.post(
            "/v1/trq-bec/coupons/redeem/authorize",
            headers=self.headers("visit-token"),
            json={
                "operation_id": begin["operation_id"],
                "session_id": begin["session_id"],
                "challenge_id": begin["challenge"]["challenge_id"],
                "device_key_id": "device:visit-test",
                "device_proof_b64u": b64u(self.visit_key.sign(proof_message)),
            },
        )
        self.assertEqual(authorized.status_code, 200, authorized.text)
        result = authorized.json()
        self.assertEqual(result["decision"], "ALLOW")
        self.assertEqual(result["quantity"], 3)
        self.assertEqual(result["amount_saved_minor"], 3_000)
        self.assertEqual(result["final_amount_minor"], 12_000)
        self.assertEqual(result["remaining_redemptions"], 5)
        self.assertEqual(self.store.products[product_id].stock_quantity, 7)
        self.assertEqual(self.store.offers[offer_id].redeemed_count, 3)
        redemption = self.store.redemptions[(offer_id, "visit-uid")]
        self.assertEqual(redemption["quantity"], 3)
        self.assertEqual(redemption["original_amount_minor"], 15_000)
        self.assertEqual(redemption["final_amount_minor"], 12_000)
        self.assertEqual(redemption["amount_saved_minor"], 3_000)

        unavailable = self.client.get(
            f"/v1/marketplace/offers/{offer_id}/qr?quantity=6",
            headers=self.headers("entre-token"),
        )
        self.assertEqual(unavailable.status_code, 409, unavailable.text)
        self.assertEqual(
            unavailable.json()["code"],
            "OFFER_QR_QUANTITY_EXCEEDS_AVAILABLE",
        )

    def test_issue_offer_accepts_eight_hour_validity(self) -> None:
        self.assertEqual(
            self.enroll("entre-token", "device:entre-test", self.entre_key).status_code,
            200,
        )
        product_id = self.prepare_product(stock_quantity=10)
        issued = self.issue_offer(
            product_id,
            maximum_redemptions=10,
            validity_minutes=480,
        )
        self.assertEqual(issued.status_code, 200, issued.text)
        self.assertEqual(issued.json()["offer"]["remaining_redemptions"], 10)

    def test_issued_offer_is_returned_by_merchant_listing(self) -> None:
        enrolled = self.enroll("entre-token", "device:entre-test", self.entre_key)
        self.assertEqual(enrolled.status_code, 200, enrolled.text)
        product_id = self.prepare_product(stock_quantity=7)
        issued = self.issue_offer(product_id, maximum_redemptions=3)
        self.assertEqual(issued.status_code, 200, issued.text)
        issued_payload = issued.json()

        response = self.client.get(
            "/v1/marketplace/offers/mine",
            headers=self.headers("entre-token"),
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()["offers"]), 1)
        listed_offer = response.json()["offers"][0]
        self.assertEqual(listed_offer["offer_id"], issued_payload["offer_id"])
        self.assertEqual(listed_offer["status"], issued_payload["offer"]["status"])
        self.assertEqual(
            listed_offer["remaining_redemptions"],
            issued_payload["offer"]["remaining_redemptions"],
        )

    def test_owner_can_reopen_qr_and_remove_finished_offer_from_catalog(self) -> None:
        enrolled = self.enroll("entre-token", "device:entre-test", self.entre_key)
        self.assertEqual(enrolled.status_code, 200, enrolled.text)
        product_id = self.prepare_product(stock_quantity=7)
        issued = self.issue_offer(product_id, maximum_redemptions=3)
        self.assertEqual(issued.status_code, 200, issued.text)
        body = issued.json()
        offer_id = body["offer_id"]

        qr = self.client.get(
            f"/v1/marketplace/offers/{offer_id}/qr",
            headers=self.headers("entre-token"),
        )
        self.assertEqual(qr.status_code, 200, qr.text)
        self.assertEqual(
            qr.json()["qr_payload"]["token_ref"],
            body["qr_payload"]["token_ref"],
        )
        self.assertEqual(qr.json()["qr_payload"]["quantity"], 1)
        self.assertRegex(
            qr.json()["qr_payload"]["quantity_proof_b64u"],
            r"^[A-Za-z0-9_-]{86}$",
        )
        self.assertEqual(qr.json()["offer"]["offer_id"], offer_id)
        self.assertTrue(
            {"intent", "envelope", "issuer_uid", "merchant_uid"}.isdisjoint(
                nested_keys(qr.json())
            )
        )

        foreign_qr = self.client.get(
            f"/v1/marketplace/offers/{offer_id}/qr",
            headers=self.headers("entre-other-token"),
        )
        self.assertEqual(foreign_qr.status_code, 404, foreign_qr.text)
        visitor_qr = self.client.get(
            f"/v1/marketplace/offers/{offer_id}/qr",
            headers=self.headers("visit-token"),
        )
        self.assertEqual(visitor_qr.status_code, 403, visitor_qr.text)

        cancelled = self.client.post(
            f"/v1/marketplace/offers/{offer_id}/status",
            headers=self.headers("entre-token"),
            json={"status": "CANCELLED"},
        )
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        unavailable_qr = self.client.get(
            f"/v1/marketplace/offers/{offer_id}/qr",
            headers=self.headers("entre-token"),
        )
        self.assertEqual(unavailable_qr.status_code, 409, unavailable_qr.text)
        self.assertEqual(
            unavailable_qr.json()["code"],
            "OFFER_QR_NOT_AVAILABLE",
        )

        deleted = self.client.delete(
            f"/v1/marketplace/offers/{offer_id}",
            headers=self.headers("entre-token"),
        )
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertEqual(deleted.json()["status"], "REVOKED")
        public_offer_ids = {
            offer.offer_id
            for product in self.store.list_public_catalog(limit=50)
            for offer in product.offers
        }
        self.assertNotIn(offer_id, public_offer_ids)
        repeated_delete = self.client.delete(
            f"/v1/marketplace/offers/{offer_id}",
            headers=self.headers("entre-token"),
        )
        self.assertEqual(repeated_delete.status_code, 404, repeated_delete.text)

    def test_catalog_feed_and_profile_publish_safe_authoritative_data(self) -> None:
        enrolled = self.enroll("entre-token", "device:entre-test", self.entre_key)
        self.assertEqual(enrolled.status_code, 200, enrolled.text)
        offered_product_id = self.prepare_product(stock_quantity=7)
        issued = self.issue_offer(offered_product_id, maximum_redemptions=3)
        self.assertEqual(issued.status_code, 200, issued.text)
        plain_product_id = self.prepare_product(price_minor=2_500, stock_quantity=4)
        stock = self.client.post(
            f"/v1/marketplace/products/{offered_product_id}/stock",
            headers=self.headers("entre-token"),
            json={"stock_quantity": 2},
        )
        self.assertEqual(stock.status_code, 200, stock.text)

        feed = self.client.get(
            "/v1/marketplace/catalog/feed?limit=50",
            headers=self.headers("visit-token"),
        )

        self.assertEqual(feed.status_code, 200, feed.text)
        items = {item["product_id"]: item for item in feed.json()["items"]}
        self.assertEqual(set(items), {offered_product_id, plain_product_id})
        offered_product = items[offered_product_id]
        self.assertEqual(
            set(offered_product),
            {
                "product_id",
                "title",
                "description",
                "price_minor",
                "currency",
                "stock_quantity",
                "created_at",
                "updated_at",
                "status",
                "status_reason",
                "ended_at",
                "merchant",
                "offers",
            },
        )
        self.assertEqual(
            offered_product["merchant"],
            {
                "firebase_uid": "entre-uid",
                "display_name": "Artesã da Feira",
                "establishment_name": "Feira LiberRotas",
            },
        )
        self.assertEqual(offered_product["stock_quantity"], 2)
        self.assertEqual(offered_product["status"], "ACTIVE")
        self.assertIsNone(offered_product["status_reason"])
        self.assertIsNone(offered_product["ended_at"])
        self.assertLessEqual(offered_product["created_at"], offered_product["updated_at"])
        self.assertEqual(len(offered_product["offers"]), 1)
        public_offer = offered_product["offers"][0]
        self.assertEqual(
            set(public_offer),
            {
                "offer_id",
                "original_amount_minor",
                "discount_amount_minor",
                "final_amount_minor",
                "currency",
                "remaining_redemptions",
                "expires_at",
                "created_at",
                "updated_at",
                "status",
                "status_reason",
                "ended_at",
            },
        )
        self.assertEqual(public_offer["offer_id"], issued.json()["offer_id"])
        self.assertEqual(public_offer["remaining_redemptions"], 2)
        self.assertEqual(public_offer["status"], "ACTIVE")
        self.assertIsNone(public_offer["status_reason"])
        self.assertIsNone(public_offer["ended_at"])
        self.assertEqual(items[plain_product_id]["offers"], [])
        self.assertTrue(
            {
                "token_ref",
                "issuer_ref",
                "qr_payload",
                "device_key_id",
                "public_key_b64u",
                "email",
                "establishment_id",
            }.isdisjoint(nested_keys(feed.json()))
        )
        limited_feed = self.client.get(
            "/v1/marketplace/catalog/feed?limit=1",
            headers=self.headers("visit-token"),
        )
        self.assertEqual(limited_feed.status_code, 200, limited_feed.text)
        self.assertEqual(len(limited_feed.json()["items"]), 1)

        profile = self.client.get(
            "/v1/marketplace/catalog/merchants/entre-uid?limit=50",
            headers=self.headers("visit-token"),
        )
        self.assertEqual(profile.status_code, 200, profile.text)
        self.assertEqual(profile.json()["merchant"], offered_product["merchant"])
        self.assertEqual(
            {product["product_id"] for product in profile.json()["products"]},
            {offered_product_id, plain_product_id},
        )

    def test_catalog_requires_bearer_and_bounds_limit(self) -> None:
        for path in (
            "/v1/marketplace/catalog/feed",
            "/v1/marketplace/catalog/merchants/entre-uid",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json()["code"], "AUTH_BEARER_REQUIRED")
        for limit in (0, 51):
            with self.subTest(limit=limit):
                response = self.client.get(
                    f"/v1/marketplace/catalog/feed?limit={limit}",
                    headers=self.headers("visit-token"),
                )
                self.assertEqual(response.status_code, 422)

    def test_catalog_hides_suspended_and_unknown_merchants_identically(self) -> None:
        self.prepare_product()
        suspended = self.client.post(
            "/internal/v1/marketplace/merchants/status",
            headers=self.headers("admin-token"),
            json={
                "firebase_uid": "entre-uid",
                "display_name": "Artesã da Feira",
                "establishment_id": "EST-FEIRA-TESTE",
                "establishment_name": "Feira LiberRotas",
                "status": "SUSPENDED",
            },
        )
        self.assertEqual(suspended.status_code, 200, suspended.text)

        feed = self.client.get(
            "/v1/marketplace/catalog/feed",
            headers=self.headers("visit-token"),
        )
        suspended_profile = self.client.get(
            "/v1/marketplace/catalog/merchants/entre-uid",
            headers=self.headers("visit-token"),
        )
        unknown_profile = self.client.get(
            "/v1/marketplace/catalog/merchants/unknown-uid",
            headers=self.headers("visit-token"),
        )

        self.assertEqual(feed.json(), {"items": []})
        self.assertEqual(suspended_profile.status_code, 404)
        self.assertEqual(unknown_profile.status_code, 404)
        self.assertEqual(suspended_profile.json(), unknown_profile.json())
        self.assertEqual(
            unknown_profile.json()["code"],
            "MERCHANT_PUBLIC_PROFILE_NOT_FOUND",
        )

    def test_catalog_keeps_paused_and_out_of_stock_but_excludes_archived_products(self) -> None:
        product_id = self.prepare_product()
        original = self.store.products[product_id]
        cases = {
            "paused": (
                replace(original, status="PAUSED"),
                ("PAUSED", "PAUSED", None),
            ),
            "archived": (replace(original, status="ARCHIVED"), None),
            "out-of-stock": (
                replace(original, stock_quantity=0),
                ("ENDED", "OUT_OF_STOCK", original.updated_at),
            ),
        }
        for name, (product, expected) in cases.items():
            with self.subTest(name=name):
                self.store.products[product_id] = product
                response = self.client.get(
                    "/v1/marketplace/catalog/feed",
                    headers=self.headers("visit-token"),
                )
                self.assertEqual(response.status_code, 200, response.text)
                if expected is None:
                    self.assertEqual(response.json(), {"items": []})
                else:
                    self.assertEqual(len(response.json()["items"]), 1)
                    public_product = response.json()["items"][0]
                    self.assertEqual(
                        (
                            public_product["status"],
                            public_product["status_reason"],
                            public_product["ended_at"],
                        ),
                        expected,
                    )
        self.store.products[product_id] = original

    def test_catalog_publishes_safe_offer_lifecycle_and_hides_internal_failure(self) -> None:
        enrolled = self.enroll("entre-token", "device:entre-test", self.entre_key)
        self.assertEqual(enrolled.status_code, 200, enrolled.text)
        product_id = self.prepare_product()
        issued = self.issue_offer(product_id, maximum_redemptions=3)
        self.assertEqual(issued.status_code, 200, issued.text)
        offer_id = issued.json()["offer_id"]
        original_offer = self.store.offers[offer_id]
        original_token = self.store.tokens[original_offer.token_ref]
        cases = {
            "paused": (
                replace(original_offer, status="PAUSED"),
                original_token,
                ("PAUSED", "PAUSED", None),
            ),
            "expired": (
                replace(original_offer, expires_at=int(time.time()) - 1),
                original_token,
                ("ENDED", "EXPIRED", int(time.time()) - 1),
            ),
            "without-balance": (
                replace(
                    original_offer,
                    redeemed_count=original_offer.maximum_redemptions,
                ),
                original_token,
                ("ENDED", "EXHAUSTED", original_offer.updated_at),
            ),
            "token-not-issued": (
                original_offer,
                replace(original_token, status="REDEEMED"),
                None,
            ),
            "revoked": (
                replace(original_offer, status="REVOKED"),
                replace(original_token, status="REVOKED"),
                None,
            ),
        }
        for name, (offer, token, expected) in cases.items():
            with self.subTest(name=name):
                self.store.offers[offer_id] = offer
                self.store.tokens[original_offer.token_ref] = token
                response = self.client.get(
                    "/v1/marketplace/catalog/feed",
                    headers=self.headers("visit-token"),
                )
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(len(response.json()["items"]), 1)
                self.assertEqual(response.json()["items"][0]["product_id"], product_id)
                public_offers = response.json()["items"][0]["offers"]
                if expected is None:
                    self.assertEqual(public_offers, [])
                else:
                    self.assertEqual(len(public_offers), 1)
                    public_offer = public_offers[0]
                    self.assertEqual(public_offer["status"], expected[0])
                    self.assertEqual(public_offer["status_reason"], expected[1])
                    if name == "expired":
                        self.assertEqual(public_offer["ended_at"], offer.expires_at)
                    else:
                        self.assertEqual(public_offer["ended_at"], expected[2])
        self.store.offers[offer_id] = original_offer
        self.store.tokens[original_offer.token_ref] = original_token

    def test_cancelled_offer_remains_in_catalog_without_token_data(self) -> None:
        self.assertEqual(
            self.enroll("entre-token", "device:entre-test", self.entre_key).status_code,
            200,
        )
        product_id = self.prepare_product(stock_quantity=3)
        issued = self.issue_offer(product_id, maximum_redemptions=2)
        self.assertEqual(issued.status_code, 200, issued.text)
        offer_id = issued.json()["offer_id"]

        cancelled = self.client.post(
            f"/v1/marketplace/offers/{offer_id}/status",
            headers=self.headers("entre-token"),
            json={"status": "CANCELLED"},
        )
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        self.assertEqual(cancelled.json()["status"], "CANCELLED")

        feed = self.client.get(
            "/v1/marketplace/catalog/feed",
            headers=self.headers("visit-token"),
        )
        self.assertEqual(feed.status_code, 200, feed.text)
        public_offer = feed.json()["items"][0]["offers"][0]
        self.assertEqual(public_offer["offer_id"], offer_id)
        self.assertEqual(public_offer["status"], "ENDED")
        self.assertEqual(public_offer["status_reason"], "CANCELLED")
        self.assertEqual(public_offer["ended_at"], public_offer["updated_at"])
        self.assertTrue(
            {"token_ref", "issuer_ref", "qr_payload", "device_key_id"}.isdisjoint(
                nested_keys(public_offer)
            )
        )

    def test_stock_end_and_product_pause_propagate_safe_offer_state(self) -> None:
        self.assertEqual(
            self.enroll("entre-token", "device:entre-test", self.entre_key).status_code,
            200,
        )
        product_id = self.prepare_product(stock_quantity=2)
        issued = self.issue_offer(product_id, maximum_redemptions=2)
        self.assertEqual(issued.status_code, 200, issued.text)

        stock = self.client.post(
            f"/v1/marketplace/products/{product_id}/stock",
            headers=self.headers("entre-token"),
            json={"stock_quantity": 0},
        )
        self.assertEqual(stock.status_code, 200, stock.text)
        ended_feed = self.client.get(
            "/v1/marketplace/catalog/feed",
            headers=self.headers("visit-token"),
        ).json()
        ended_product = ended_feed["items"][0]
        ended_offer = ended_product["offers"][0]
        self.assertEqual(
            (ended_product["status"], ended_product["status_reason"]),
            ("ENDED", "OUT_OF_STOCK"),
        )
        self.assertEqual(
            (ended_offer["status"], ended_offer["status_reason"]),
            ("ENDED", "OUT_OF_STOCK"),
        )
        self.assertEqual(ended_offer["ended_at"], ended_product["ended_at"])

        original = self.store.products[product_id]
        self.store.products[product_id] = replace(original, stock_quantity=2, status="PAUSED")
        paused_feed = self.client.get(
            "/v1/marketplace/catalog/feed",
            headers=self.headers("visit-token"),
        ).json()
        paused_product = paused_feed["items"][0]
        paused_offer = paused_product["offers"][0]
        self.assertEqual(
            (paused_product["status"], paused_product["status_reason"], paused_product["ended_at"]),
            ("PAUSED", "PAUSED", None),
        )
        self.assertEqual(
            (paused_offer["status"], paused_offer["status_reason"], paused_offer["ended_at"]),
            ("PAUSED", "PRODUCT_PAUSED", None),
        )

    def test_visitor_cannot_issue_coupon(self) -> None:
        self.assertEqual(self.enroll("visit-token", "device:visit-test", self.visit_key).status_code, 200)
        response = self.client.post(
            "/v1/trq-bec/coupons/issue",
            headers=self.headers("visit-token"),
            json={
                "product_id": "PROD-A1B2C3D4E5F6",
                "discount_type": "PERCENT",
                "discount_value": 20,
                "maximum_redemptions": 1,
                "valid_until": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
                "purpose": "LIVE_FAIR_DISCOUNT",
                "device_key_id": "device:visit-test",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "ENTREPRENEUR_ACCESS_REQUIRED")

    def test_device_key_cannot_be_rebound(self) -> None:
        first = self.enroll("visit-token", "device:shared-test", self.visit_key)
        second = self.enroll("entre-token", "device:shared-test", self.entre_key)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)

    def test_web_crypto_indexeddb_storage_profile_is_accepted(self) -> None:
        response = self.enroll(
            "visit-token",
            "device:web-visit-test",
            self.visit_key,
            storage_profile="WEB_CRYPTO_INDEXEDDB_LAB",
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "ENROLLED")
        self.assertEqual(
            self.store.devices["device:web-visit-test"].storage_profile,
            "WEB_CRYPTO_INDEXEDDB_LAB",
        )

    def test_every_new_visitor_device_is_active_and_sends_alert(self) -> None:
        first = self.enroll(
            "visit-token",
            "device:visitor-primary",
            self.visit_key,
        )
        additional_key = Ed25519PrivateKey.generate()
        additional = self.enroll(
            "visit-token",
            "device:visitor-additional",
            additional_key,
        )

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["device_status"], "ACTIVE")
        self.assertEqual(first.json()["notification_status"], "SENT")
        self.assertEqual(additional.status_code, 200, additional.text)
        self.assertEqual(additional.json()["device_status"], "ACTIVE")
        self.assertEqual(additional.json()["notification_status"], "SENT")
        self.assertTrue(additional.json()["is_additional_device"])
        self.assertEqual(len(self.device_notifier.calls), 2)
        self.assertEqual([call[3] for call in self.device_notifier.calls], [0, 0])
        self.assertIsNotNone(
            self.store.get_device("visit-uid", "device:visitor-additional")
        )

        repeated = self.enroll(
            "visit-token",
            "device:visitor-additional",
            additional_key,
        )
        self.assertEqual(repeated.status_code, 200, repeated.text)
        self.assertEqual(repeated.json()["status"], "ALREADY_ENROLLED")
        self.assertEqual(repeated.json()["device_status"], "ACTIVE")
        self.assertEqual(len(self.device_notifier.calls), 2)

    def test_every_new_entrepreneur_device_uses_security_cooldown(self) -> None:
        first = self.enroll(
            "entre-token",
            "device:entre-primary",
            self.entre_key,
            device_name="Celular principal",
            platform="android",
            model_name="Modelo de teste",
            app_version="1.0.0",
        )
        additional_key = Ed25519PrivateKey.generate()
        additional = self.enroll(
            "entre-token",
            "device:entre-additional",
            additional_key,
            storage_profile="WEB_CRYPTO_INDEXEDDB_LAB",
            device_name="Navegador pessoal",
            platform="web",
            model_name="Chrome",
            app_version="1.0.0",
        )

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["device_status"], "PENDING_APPROVAL")
        self.assertEqual(first.json()["notification_status"], "SENT")
        self.assertFalse(first.json()["is_additional_device"])
        self.assertEqual(additional.status_code, 200, additional.text)
        self.assertEqual(additional.json()["device_status"], "PENDING_APPROVAL")
        self.assertEqual(additional.json()["notification_status"], "SENT")
        self.assertTrue(additional.json()["is_additional_device"])
        self.assertEqual(len(self.device_notifier.calls), 2)
        self.assertEqual([call[3] for call in self.device_notifier.calls], [600, 600])
        approval_token = self.device_notifier.calls[1][2]
        self.assertRegex(approval_token, r"^[A-Za-z0-9_-]{32,128}$")
        self.assertNotIn(approval_token, repr(self.store.devices))
        self.assertIsNone(self.store.get_device("entre-uid", "device:entre-additional"))

        repeated = self.enroll(
            "entre-token",
            "device:entre-additional",
            additional_key,
            storage_profile="WEB_CRYPTO_INDEXEDDB_LAB",
            device_name="Navegador pessoal",
            platform="web",
            model_name="Chrome",
            app_version="1.0.0",
        )
        self.assertEqual(repeated.status_code, 200, repeated.text)
        self.assertEqual(repeated.json()["status"], "ALREADY_ENROLLED")
        self.assertEqual(repeated.json()["device_status"], "PENDING_APPROVAL")
        self.assertEqual(len(self.device_notifier.calls), 2)

        listed = self.client.get(
            "/v1/account/devices", headers=self.headers("entre-token")
        )
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(len(listed.json()["devices"]), 2)
        self.assertNotIn("public_key_b64u", nested_keys(listed.json()))
        self.assertNotIn("approval_token", nested_keys(listed.json()))
        self.assertNotIn("approval_token_hash", nested_keys(listed.json()))

        wrong_account = self.client.post(
            "/v1/account/devices/approve",
            headers=self.headers("entre-other-token"),
            json={"approval_token": approval_token},
        )
        self.assertEqual(wrong_account.status_code, 400, wrong_account.text)
        self.assertEqual(
            wrong_account.json()["code"], "DEVICE_APPROVAL_INVALID_OR_EXPIRED"
        )
        approved = self.client.post(
            "/v1/account/devices/approve",
            headers=self.headers("entre-token"),
            json={"approval_token": approval_token},
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()["device_status"], "ACTIVE")
        self.assertIsNotNone(
            self.store.get_device("entre-uid", "device:entre-additional")
        )
        reused = self.client.post(
            "/v1/account/devices/approve",
            headers=self.headers("entre-token"),
            json={"approval_token": approval_token},
        )
        self.assertEqual(reused.status_code, 400, reused.text)

    def test_first_institution_device_uses_ten_minute_cooldown(self) -> None:
        response = self.enroll(
            "institution-token",
            "device:institution-primary",
            Ed25519PrivateKey.generate(),
            device_name="Computador da instituição",
            platform="windows",
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["device_status"], "PENDING_APPROVAL")
        self.assertEqual(response.json()["notification_status"], "SENT")
        self.assertFalse(response.json()["is_additional_device"])
        self.assertEqual(self.device_notifier.calls[-1][3], 600)
        self.assertIsNone(
            self.store.get_device("institution-uid", "device:institution-primary")
        )

    def test_device_approval_resend_rotates_token_with_cooldown(self) -> None:
        self.enroll("entre-token", "device:resend-primary", self.entre_key)
        additional_key = Ed25519PrivateKey.generate()
        self.enroll("entre-token", "device:resend-pending", additional_key)
        old_token = self.device_notifier.calls[-1][2]

        immediate = self.client.post(
            "/v1/account/devices/resend-approval",
            headers=self.headers("entre-token"),
            json={"device_key_id": "device:resend-pending"},
        )
        self.assertEqual(immediate.status_code, 429, immediate.text)
        self.assertEqual(immediate.json()["code"], "APPROVAL_RESEND_COOLDOWN")
        stale_auth = self.client.post(
            "/v1/account/devices/resend-approval",
            headers=self.headers("stale-entre-token"),
            json={"device_key_id": "device:resend-pending"},
        )
        self.assertEqual(stale_auth.status_code, 403, stale_auth.text)
        self.assertEqual(stale_auth.json()["code"], "RECENT_AUTHENTICATION_REQUIRED")

        pending = self.store.devices["device:resend-pending"]
        self.store.devices["device:resend-pending"] = replace(
            pending,
            approval_last_sent_at=datetime.now(timezone.utc) - timedelta(seconds=61),
        )
        resent = self.client.post(
            "/v1/account/devices/resend-approval",
            headers=self.headers("entre-token"),
            json={"device_key_id": "device:resend-pending"},
        )
        self.assertEqual(resent.status_code, 200, resent.text)
        self.assertEqual(resent.json()["notification_status"], "SENT")
        new_token = self.device_notifier.calls[-1][2]
        self.assertNotEqual(old_token, new_token)

        invalidated = self.client.post(
            "/v1/account/devices/approve",
            headers=self.headers("entre-token"),
            json={"approval_token": old_token},
        )
        self.assertEqual(invalidated.status_code, 400, invalidated.text)
        approved = self.client.post(
            "/v1/account/devices/approve",
            headers=self.headers("entre-token"),
            json={"approval_token": new_token},
        )
        self.assertEqual(approved.status_code, 200, approved.text)

    def test_expired_device_approval_token_is_rejected(self) -> None:
        self.enroll("entre-token", "device:expired-primary", self.entre_key)
        self.enroll(
            "entre-token",
            "device:expired-pending",
            Ed25519PrivateKey.generate(),
        )
        approval_token = self.device_notifier.calls[-1][2]
        pending = self.store.devices["device:expired-pending"]
        self.store.devices["device:expired-pending"] = replace(
            pending,
            approval_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        expired = self.client.post(
            "/v1/account/devices/approve",
            headers=self.headers("entre-token"),
            json={"approval_token": approval_token},
        )
        self.assertEqual(expired.status_code, 400, expired.text)
        self.assertEqual(
            expired.json()["code"], "DEVICE_APPROVAL_INVALID_OR_EXPIRED"
        )
        self.assertEqual(
            self.store.devices["device:expired-pending"].status,
            "ACTIVE",
        )
        self.assertIsNotNone(
            self.store.get_device("entre-uid", "device:expired-pending")
        )

    def test_invalid_approval_token_is_not_echoed_by_validation_error(self) -> None:
        raw_secret = "approval-token-<NAO-PODE-ECOAR>-1234567890"
        response = self.client.post(
            "/v1/account/devices/approve",
            headers=self.headers("visit-token"),
            json={"approval_token": raw_secret},
        )
        self.assertEqual(response.status_code, 422, response.text)
        self.assertNotIn(raw_secret, response.text)
        self.assertNotIn("input", nested_keys(response.json()))

    def test_pending_device_cannot_issue_an_offer_before_approval(self) -> None:
        self.enroll("entre-token", "device:entre-primary", self.entre_key)
        self.enroll(
            "entre-token",
            "device:entre-pending",
            Ed25519PrivateKey.generate(),
        )
        product_id = self.prepare_product()
        denied = self.client.post(
            "/v1/trq-bec/coupons/issue",
            headers=self.headers("entre-token"),
            json={
                "product_id": product_id,
                "discount_type": "PERCENT",
                "discount_value": 20,
                "maximum_redemptions": 1,
                "valid_until": (
                    datetime.now(timezone.utc) + timedelta(minutes=5)
                ).isoformat(),
                "purpose": "LIVE_FAIR_DISCOUNT",
                "device_key_id": "device:entre-pending",
            },
        )
        self.assertEqual(denied.status_code, 403, denied.text)
        self.assertEqual(denied.json()["code"], "DEVICE_NOT_ENROLLED")

    def test_email_failure_does_not_block_login_or_activate_additional_device(self) -> None:
        self.enroll("entre-token", "device:email-primary", self.entre_key)
        self.device_notifier.fail = True
        additional = self.enroll(
            "entre-token",
            "device:email-pending",
            Ed25519PrivateKey.generate(),
        )
        self.assertEqual(additional.status_code, 200, additional.text)
        self.assertEqual(additional.json()["device_status"], "PENDING_APPROVAL")
        self.assertEqual(additional.json()["notification_status"], "FAILED")
        self.assertEqual(
            self.store.devices["device:email-pending"].notification_status,
            "FAILED",
        )
        pending = self.store.devices["device:email-pending"]
        self.store.devices["device:email-pending"] = replace(
            pending,
            approval_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        listed = self.client.get(
            "/v1/account/devices", headers=self.headers("entre-token")
        )
        self.assertEqual(listed.status_code, 200, listed.text)
        activated = next(
            item
            for item in listed.json()["devices"]
            if item["device_key_id"] == "device:email-pending"
        )
        self.assertEqual(activated["status"], "ACTIVE")

    def test_revoke_all_blocks_devices_before_revoking_firebase_sessions(self) -> None:
        self.enroll("entre-token", "device:revoke-primary", self.entre_key)
        pending_key = Ed25519PrivateKey.generate()
        self.enroll("entre-token", "device:revoke-pending", pending_key)
        self.session_revoker.fail = True

        failed = self.client.post(
            "/v1/account/devices/revoke-all",
            headers=self.headers("entre-token"),
        )
        self.assertEqual(failed.status_code, 503, failed.text)
        self.assertEqual(failed.json()["code"], "SESSION_REVOCATION_FAILED")
        self.assertTrue(
            all(item.status == "REVOKED" for item in self.store.devices.values())
        )
        self.assertEqual(self.store.events[-1]["event_type"], "DEVICE_KEYS_REVOKED")
        self.assertNotIn(
            "FIREBASE_SESSIONS_REVOKED",
            [event["event_type"] for event in self.store.events],
        )

        self.session_revoker.fail = False
        retried = self.client.post(
            "/v1/account/devices/revoke-all",
            headers=self.headers("entre-token"),
        )
        self.assertEqual(retried.status_code, 200, retried.text)
        self.assertEqual(retried.json()["revoked_devices"], 0)
        self.assertTrue(retried.json()["sessions_revoked"])
        self.assertEqual(self.session_revoker.calls, ["entre-uid", "entre-uid"])
        self.assertEqual(
            [event["event_type"] for event in self.store.events[-2:]],
            ["DEVICE_KEYS_REVOKED", "FIREBASE_SESSIONS_REVOKED"],
        )

        revoked_reenroll = self.enroll(
            "entre-token", "device:revoke-primary", self.entre_key
        )
        self.assertEqual(revoked_reenroll.status_code, 409, revoked_reenroll.text)
        self.assertEqual(revoked_reenroll.json()["code"], "DEVICE_KEY_REVOKED")
        replacement = self.enroll(
            "entre-token",
            "device:revoke-replacement",
            Ed25519PrivateKey.generate(),
        )
        self.assertEqual(replacement.status_code, 200, replacement.text)
        self.assertEqual(replacement.json()["device_status"], "PENDING_APPROVAL")
        self.assertIsNone(
            self.store.get_device("entre-uid", "device:revoke-replacement")
        )
        approved = self.client.post(
            "/v1/account/devices/approve",
            headers=self.headers("entre-token"),
            json={"approval_token": self.device_notifier.calls[-1][2]},
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertIsNotNone(
            self.store.get_device("entre-uid", "device:revoke-replacement")
        )

    def test_firebase_revoke_success_is_not_rolled_back_by_late_audit_failure(self) -> None:
        self.enroll("visit-token", "device:audit-primary", self.visit_key)
        with patch.object(
            self.service,
            "_append_event",
            side_effect=ConnectionError("audit unavailable"),
        ):
            response = self.client.post(
                "/v1/account/devices/revoke-all",
                headers=self.headers("visit-token"),
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["sessions_revoked"])
        self.assertEqual(self.session_revoker.calls, ["visit-uid"])
        self.assertEqual(
            self.store.devices["device:audit-primary"].status,
            "REVOKED",
        )
        self.assertEqual(self.store.events[-1]["event_type"], "DEVICE_KEYS_REVOKED")

    def test_pending_device_limit_prevents_unbounded_security_email_spam(self) -> None:
        self.enroll("entre-token", "device:limit-primary", self.entre_key)
        for index in range(4):
            response = self.enroll(
                "entre-token",
                f"device:limit-pending-{index}",
                Ed25519PrivateKey.generate(),
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["device_status"], "PENDING_APPROVAL")
        blocked = self.enroll(
            "entre-token",
            "device:limit-pending-overflow",
            Ed25519PrivateKey.generate(),
        )
        self.assertEqual(blocked.status_code, 429, blocked.text)
        self.assertEqual(blocked.json()["code"], "PENDING_DEVICE_LIMIT_REACHED")
        self.assertEqual(len(self.device_notifier.calls), 5)

    def test_finished_cooldown_activates_device_before_pending_limit_count(self) -> None:
        self.service.settings.device_max_pending_per_account = 1
        self.enroll("entre-token", "device:expiry-limit-primary", self.entre_key)
        primary = self.store.devices["device:expiry-limit-primary"]
        self.store.devices["device:expiry-limit-primary"] = replace(
            primary,
            approval_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        activated = self.client.get(
            "/v1/account/devices",
            headers=self.headers("entre-token"),
        )
        self.assertEqual(activated.status_code, 200, activated.text)
        self.enroll(
            "entre-token",
            "device:expiry-limit-old",
            Ed25519PrivateKey.generate(),
        )
        old_pending = self.store.devices["device:expiry-limit-old"]
        self.store.devices["device:expiry-limit-old"] = replace(
            old_pending,
            approval_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )

        replacement = self.enroll(
            "entre-token",
            "device:expiry-limit-new",
            Ed25519PrivateKey.generate(),
        )
        self.assertEqual(replacement.status_code, 200, replacement.text)
        self.assertEqual(replacement.json()["device_status"], "PENDING_APPROVAL")
        self.assertEqual(
            self.store.devices["device:expiry-limit-old"].status,
            "ACTIVE",
        )
        self.assertIsNone(
            self.store.devices["device:expiry-limit-old"].approval_expires_at
        )
        self.assertNotIn("device:expiry-limit-old", self.store.device_approval_hashes)
        self.assertEqual(
            sum(
                item.status == "PENDING_APPROVAL"
                for item in self.store.devices.values()
                if item.firebase_uid == "entre-uid"
            ),
            1,
        )

    def test_unknown_storage_profile_is_rejected(self) -> None:
        response = self.enroll(
            "visit-token",
            "device:invalid-profile",
            self.visit_key,
            storage_profile="LOCAL_STORAGE_UNSAFE",
        )

        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(response.json()["detail"][0]["loc"], ["body", "storage_profile"])
        self.assertNotIn("device:invalid-profile", self.store.devices)

    def test_wrong_device_proof_is_denied(self) -> None:
        self.assertEqual(self.enroll("entre-token", "device:entre-test", self.entre_key).status_code, 200)
        self.assertEqual(self.enroll("visit-token", "device:visit-test", self.visit_key).status_code, 200)
        issued = self.issue_offer(self.prepare_product())
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

    def test_expo_web_dev_origins_have_cors_preflight(self) -> None:
        for origin in ("http://127.0.0.1:8082", "http://localhost:8082"):
            for path, method in (
                ("/v1/trq-bec/devices/enroll", "POST"),
                ("/v1/institution/profile", "PATCH"),
            ):
                with self.subTest(origin=origin, method=method):
                    response = self.client.options(
                        path,
                        headers={
                            "origin": origin,
                            "access-control-request-method": method,
                            "access-control-request-headers": "authorization,content-type",
                        },
                    )
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(response.headers["access-control-allow-origin"], origin)

    def test_openapi_contract_is_grouped_secured_and_public_only(self) -> None:
        schema = self.client.get("/openapi.json").json()
        self.assertEqual(
            [tag["name"] for tag in schema["tags"]],
            [
                "Saúde e prontidão",
                "Administracao",
                "Suporte",
                "Seguranca",
                "Instituicao",
                "Dispositivos",
                "Marketplace",
                "Comunidade",
                "Cupons",
                "Resgate",
            ],
        )
        self.assertNotIn("/internal/v1/ledger/checkpoint", schema["paths"])
        security_scheme = schema["components"]["securitySchemes"]["FirebaseIDToken"]
        self.assertEqual(security_scheme["type"], "http")
        self.assertEqual(security_scheme["scheme"], "bearer")
        issue = schema["paths"]["/v1/trq-bec/coupons/issue"]["post"]
        self.assertEqual(issue["security"], [{"FirebaseIDToken": []}])
        self.assertIn("503", issue["responses"])
        feed = schema["paths"]["/v1/marketplace/catalog/feed"]["get"]
        profile = schema["paths"]["/v1/marketplace/catalog/merchants/{firebase_uid}"]["get"]
        self.assertEqual(feed["security"], [{"FirebaseIDToken": []}])
        self.assertEqual(profile["security"], [{"FirebaseIDToken": []}])
        self.assertEqual(
            profile["responses"]["404"]["content"]["application/json"]["examples"][
                "perfilIndisponivel"
            ]["value"]["code"],
            "MERCHANT_PUBLIC_PROFILE_NOT_FOUND",
        )
        storage_profile = schema["components"]["schemas"]["EnrollDeviceRequest"]["properties"][
            "storage_profile"
        ]
        self.assertEqual(
            storage_profile["enum"],
            ["EXPO_SECURE_STORE_LAB", "WEB_CRYPTO_INDEXEDDB_LAB"],
        )
        self.assertNotIn("security", schema["paths"]["/health/"]["get"])
        self.assertNotIn("security", schema["paths"]["/v1/time"]["get"])
        for path, method in (
            ("/v1/admin/institutions", "post"),
            ("/v1/admin/accounts", "get"),
            ("/v1/admin/operations/summary", "get"),
            ("/v1/support/institutions", "post"),
            ("/v1/support/accounts", "get"),
            ("/v1/security/accounts", "get"),
            ("/v1/security/monitoring/summary", "get"),
            ("/v1/security/accounts/{uid}/status", "post"),
            ("/v1/institution/profile", "get"),
            ("/v1/institution/profile", "patch"),
            ("/v1/institution/reports/summary", "get"),
            ("/v1/institution/groups", "post"),
            ("/v1/institution/groups/{group_id}/close", "post"),
        ):
            self.assertEqual(
                schema["paths"][path][method]["security"],
                [{"FirebaseIDToken": []}],
            )
        status_request = schema["components"]["schemas"]["AccessAccountStatusRequest"]
        self.assertEqual(set(status_request["required"]), {"status", "reason"})


    def test_internal_openapi_is_isolated_from_public_contract(self) -> None:
        schema = self.client.get("/internal/openapi.json").json()
        self.assertEqual([tag["name"] for tag in schema["tags"]], ["Operações internas"])
        self.assertEqual(
            set(schema["paths"]),
            {"/internal/v1/ledger/checkpoint", "/internal/v1/marketplace/merchants/status"},
        )
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
            "PRODUCT_NOT_ACTIVE_OR_NOT_OWNED",
        )
        authorize = schema["paths"]["/v1/trq-bec/coupons/redeem/authorize"]["post"]
        unavailable_examples = authorize["responses"]["503"]["content"]["application/json"]["examples"]
        self.assertEqual(
            unavailable_examples["replayIndisponivel"]["value"]["code"],
            "REPLAY_STORE_UNAVAILABLE",
        )

    def test_authoritative_public_profile_reserves_unique_normalized_names(self) -> None:
        created = self.save_public_profile("visit-token", "João da Praça")
        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(created.json()["uid"], "visit-uid")
        self.assertEqual(created.json()["role"], "visitor")
        self.assertEqual(
            self.community.profiles["visit-uid"].display_name,
            "João da Praça",
        )

        duplicate = self.save_public_profile("entre-token", "  joao   da praca  ")
        self.assertEqual(duplicate.status_code, 409, duplicate.text)
        self.assertEqual(duplicate.json()["code"], "DISPLAY_NAME_ALREADY_IN_USE")

        reserved = self.save_public_profile("entre-token", "Suporte LiberRotas")
        self.assertEqual(reserved.status_code, 409, reserved.text)
        self.assertEqual(reserved.json()["code"], "DISPLAY_NAME_RESERVED")

        staff = self.save_public_profile("support-token", "Equipe Pública")
        self.assertEqual(staff.status_code, 403, staff.text)
        self.assertEqual(staff.json()["code"], "PUBLIC_PROFILE_ROLE_REQUIRED")

        public_read = self.client.get(
            "/v1/profile/public/visit-uid",
            headers=self.headers("visit-token"),
        )
        self.assertEqual(public_read.status_code, 200, public_read.text)
        self.assertNotIn("email", nested_keys(public_read.json()))

    def test_global_search_combines_active_public_content_and_excludes_staff(self) -> None:
        self.assertEqual(
            self.save_public_profile("visit-token", "Visitante Café").status_code,
            200,
        )
        self.assertEqual(
            self.save_public_profile("entre-token", "Ateliê do Café").status_code,
            200,
        )
        product_id = self.prepare_product()
        post = self.client.post(
            "/v1/community/posts",
            headers=self.headers("entre-token"),
            json={"text": "Encontro do café artesanal"},
        )
        self.assertEqual(post.status_code, 201, post.text)

        result = self.client.get(
            "/v1/search?q=cafe&types=PROFILE,POST&limit=20",
            headers=self.headers("visit-token"),
        )
        self.assertEqual(result.status_code, 200, result.text)
        result_types = {item["type"] for item in result.json()["items"]}
        self.assertEqual(result_types, {"PROFILE", "POST"})
        self.assertNotIn("support-uid", str(result.json()))
        self.assertNotIn("@example.test", str(result.json()))

        product_result = self.client.get(
            "/v1/search?q=bordado&types=PRODUCT&limit=20",
            headers=self.headers("visit-token"),
        )
        self.assertEqual(product_result.status_code, 200, product_result.text)
        self.assertEqual(product_result.json()["items"][0]["id"], product_id)

    def test_direct_messages_derive_sender_enforce_membership_and_blocks(self) -> None:
        self.assertEqual(self.save_public_profile("visit-token", "Pessoa Visitante").status_code, 200)
        self.assertEqual(self.save_public_profile("entre-token", "Pessoa Empreendedora").status_code, 200)
        self.assertEqual(
            self.save_public_profile("institution-token", "Instituição Parceira").status_code,
            200,
        )

        injected_sender = self.client.post(
            "/v1/messages",
            headers=self.headers("visit-token"),
            json={
                "recipient_uid": "entre-uid",
                "content": "Mensagem segura",
                "sender_uid": "admin-uid",
            },
        )
        self.assertEqual(injected_sender.status_code, 422, injected_sender.text)

        created = self.client.post(
            "/v1/messages",
            headers=self.headers("visit-token"),
            json={"recipient_uid": "entre-uid", "content": "Olá, empreendedor"},
        )
        self.assertEqual(created.status_code, 201, created.text)
        conversation_id = created.json()["conversation"]["conversation_id"]
        first_message = created.json()["messages"][0]
        self.assertEqual(first_message["sender"]["uid"], "visit-uid")
        self.assertNotIn("email", nested_keys(created.json()))

        outsider = self.client.get(
            f"/v1/messages/conversations/{conversation_id}",
            headers=self.headers("institution-token"),
        )
        self.assertEqual(outsider.status_code, 404, outsider.text)

        blocked = self.client.post(
            "/v1/messages/blocks/visit-uid",
            headers=self.headers("entre-token"),
        )
        self.assertEqual(blocked.status_code, 200, blocked.text)
        blocker_view = self.client.get(
            f"/v1/messages/conversations/{conversation_id}",
            headers=self.headers("entre-token"),
        )
        self.assertTrue(blocker_view.json()["conversation"]["blocked_by_me"])
        self.assertFalse(blocker_view.json()["conversation"]["can_message"])
        blocked_view = self.client.get(
            f"/v1/messages/conversations/{conversation_id}",
            headers=self.headers("visit-token"),
        )
        self.assertTrue(blocked_view.json()["conversation"]["blocked_me"])
        self.assertFalse(blocked_view.json()["conversation"]["can_message"])
        denied = self.client.post(
            f"/v1/messages/conversations/{conversation_id}/messages",
            headers=self.headers("visit-token"),
            json={"content": "Esta mensagem não será entregue"},
        )
        self.assertEqual(denied.status_code, 409, denied.text)
        self.assertEqual(denied.json()["code"], "MESSAGE_DELIVERY_BLOCKED")

        read = self.client.post(
            f"/v1/messages/conversations/{conversation_id}/read",
            headers=self.headers("entre-token"),
        )
        self.assertEqual(read.status_code, 200, read.text)

    def test_private_message_image_is_visible_only_to_conversation_members(self) -> None:
        self.assertEqual(self.save_public_profile("visit-token", "Visitante com Foto").status_code, 200)
        self.assertEqual(self.save_public_profile("entre-token", "Empreendedor com Foto").status_code, 200)
        self.assertEqual(
            self.save_public_profile("institution-token", "Instituição sem Acesso").status_code,
            200,
        )
        created = self.client.post(
            "/v1/messages",
            headers=self.headers("visit-token"),
            json={"recipient_uid": "entre-uid", "content": "Início da conversa"},
        )
        self.assertEqual(created.status_code, 201, created.text)
        conversation_id = created.json()["conversation"]["conversation_id"]

        raw_image = b"\xff\xd8\xff-private-message"
        authorized = self.client.post(
            "/v1/media/uploads",
            headers=self.headers("visit-token"),
            json={
                "entity_type": "support",
                "entity_id": conversation_id,
                "media_role": "support_attachment",
                "original_filename": "mensagem.jpg",
                "content_type": "image/jpeg",
                "size_bytes": len(raw_image),
                "client_request_id": "private-message-image-001",
            },
        )
        self.assertEqual(authorized.status_code, 201, authorized.text)
        authorization = authorized.json()
        self.media_storage.simulate_signed_put(authorization, raw_image)
        processed_bytes = b"\xff\xd8\xff-private-message-processed"
        processed = ProcessedImage(
            data=processed_bytes,
            content_type="image/jpeg",
            width=800,
            height=600,
            checksum_sha256=hashlib.sha256(processed_bytes).hexdigest(),
        )
        with patch("trq_bec.server.service.process_image", return_value=processed):
            confirmed = self.client.post(
                f"/v1/media/uploads/{authorization['media_id']}/confirm",
                headers=self.headers("visit-token"),
            )
        self.assertEqual(confirmed.status_code, 200, confirmed.text)

        sent = self.client.post(
            f"/v1/messages/conversations/{conversation_id}/messages",
            headers=self.headers("visit-token"),
            json={
                "content": "Foto do produto",
                "media_id": authorization["media_id"],
            },
        )
        self.assertEqual(sent.status_code, 201, sent.text)
        self.assertEqual(sent.json()["media_id"], authorization["media_id"])

        recipient_view = self.client.get(
            f"/v1/media/{authorization['media_id']}",
            headers=self.headers("entre-token"),
        )
        self.assertEqual(recipient_view.status_code, 200, recipient_view.text)
        outsider_view = self.client.get(
            f"/v1/media/{authorization['media_id']}",
            headers=self.headers("institution-token"),
        )
        self.assertEqual(outsider_view.status_code, 403, outsider_view.text)

        forged_attachment = self.client.post(
            f"/v1/messages/conversations/{conversation_id}/messages",
            headers=self.headers("entre-token"),
            json={
                "content": "Tentativa de reutilizar imagem alheia",
                "media_id": authorization["media_id"],
            },
        )
        self.assertEqual(forged_attachment.status_code, 403, forged_attachment.text)
        self.assertEqual(forged_attachment.json()["code"], "MESSAGE_MEDIA_FORBIDDEN")

    def test_post_comments_support_replies_and_likes(self) -> None:
        self.assertEqual(self.save_public_profile("visit-token", "Visitante Comentando").status_code, 200)
        self.assertEqual(self.save_public_profile("entre-token", "Empreendedor Respondendo").status_code, 200)
        published = self.client.post(
            "/v1/community/posts",
            headers=self.headers("entre-token"),
            json={"text": "Publicação aberta para comentários"},
        )
        self.assertEqual(published.status_code, 201, published.text)
        post_id = published.json()["document_id"]

        root = self.client.post(
            f"/v1/feed/posts/{post_id}/comments",
            headers=self.headers("visit-token"),
            json={"content": "Gostei desta publicação", "client_comment_id": "comment-root-001"},
        )
        self.assertEqual(root.status_code, 201, root.text)
        root_id = root.json()["comment_id"]
        self.assertEqual(root.json()["author"]["uid"], "visit-uid")

        reply = self.client.post(
            f"/v1/feed/posts/{post_id}/comments",
            headers=self.headers("entre-token"),
            json={
                "content": "Obrigado pelo comentário",
                "parent_comment_id": root_id,
                "client_comment_id": "comment-reply-001",
            },
        )
        self.assertEqual(reply.status_code, 201, reply.text)
        reply_id = reply.json()["comment_id"]

        nested = self.client.post(
            f"/v1/feed/posts/{post_id}/comments",
            headers=self.headers("visit-token"),
            json={
                "content": "Resposta de terceiro nível",
                "parent_comment_id": reply_id,
                "client_comment_id": "comment-nested-001",
            },
        )
        self.assertEqual(nested.status_code, 409, nested.text)
        self.assertEqual(nested.json()["code"], "COMMUNITY_COMMENT_REPLY_DEPTH_EXCEEDED")

        liked = self.client.put(
            f"/v1/feed/comments/{reply_id}/like",
            headers=self.headers("visit-token"),
        )
        self.assertEqual(liked.status_code, 200, liked.text)
        self.assertTrue(liked.json()["liked"])
        self.assertEqual(liked.json()["like_count"], 1)

        listed = self.client.get(
            f"/v1/feed/posts/{post_id}/comments",
            headers=self.headers("visit-token"),
        )
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(len(listed.json()["comments"]), 2)
        reply_view = next(
            item for item in listed.json()["comments"] if item["comment_id"] == reply_id
        )
        self.assertTrue(reply_view["liked_by_me"])
        self.assertEqual(reply_view["like_count"], 1)

        unliked = self.client.delete(
            f"/v1/feed/comments/{reply_id}/like",
            headers=self.headers("visit-token"),
        )
        self.assertEqual(unliked.status_code, 200, unliked.text)
        self.assertFalse(unliked.json()["liked"])
        self.assertEqual(unliked.json()["like_count"], 0)

    def test_post_and_comment_authors_can_edit_and_delete_their_content(self) -> None:
        self.assertEqual(self.save_public_profile("visit-token", "Visitante Autor").status_code, 200)
        self.assertEqual(self.save_public_profile("entre-token", "Empreendedor Autor").status_code, 200)
        published = self.client.post(
            "/v1/community/posts",
            headers=self.headers("entre-token"),
            json={"text": "Texto original"},
        )
        self.assertEqual(published.status_code, 201, published.text)
        post_id = published.json()["document_id"]

        forbidden_post_edit = self.client.patch(
            f"/v1/community/posts/{post_id}",
            headers=self.headers("visit-token"),
            json={"text": "Tentativa alheia"},
        )
        self.assertEqual(forbidden_post_edit.status_code, 403, forbidden_post_edit.text)

        edited_post = self.client.patch(
            f"/v1/community/posts/{post_id}",
            headers=self.headers("entre-token"),
            json={"text": "Texto corrigido"},
        )
        self.assertEqual(edited_post.status_code, 200, edited_post.text)
        self.assertEqual(edited_post.json()["status"], "updated")

        comment = self.client.post(
            f"/v1/feed/posts/{post_id}/comments",
            headers=self.headers("visit-token"),
            json={"content": "Comentário original", "client_comment_id": "comment-edit-001"},
        )
        self.assertEqual(comment.status_code, 201, comment.text)
        comment_id = comment.json()["comment_id"]

        forbidden_comment_edit = self.client.patch(
            f"/v1/feed/comments/{comment_id}",
            headers=self.headers("entre-token"),
            json={"content": "Tentativa alheia"},
        )
        self.assertEqual(forbidden_comment_edit.status_code, 403, forbidden_comment_edit.text)

        edited_comment = self.client.patch(
            f"/v1/feed/comments/{comment_id}",
            headers=self.headers("visit-token"),
            json={"content": "Comentário corrigido"},
        )
        self.assertEqual(edited_comment.status_code, 200, edited_comment.text)
        self.assertEqual(edited_comment.json()["content"], "Comentário corrigido")
        self.assertIsNotNone(edited_comment.json()["updated_at"])

        deleted_comment = self.client.delete(
            f"/v1/feed/comments/{comment_id}",
            headers=self.headers("visit-token"),
        )
        self.assertEqual(deleted_comment.status_code, 200, deleted_comment.text)
        self.assertEqual(deleted_comment.json()["status"], "deleted")

        deleted_post = self.client.delete(
            f"/v1/community/posts/{post_id}",
            headers=self.headers("entre-token"),
        )
        self.assertEqual(deleted_post.status_code, 200, deleted_post.text)
        self.assertEqual(deleted_post.json()["status"], "deleted")
        self.assertNotIn(post_id, self.community.posts)

    def test_support_inbox_uses_virtual_staff_identity_and_resolves_request(self) -> None:
        self.assertEqual(self.save_public_profile("visit-token", "Pessoa com Dúvida").status_code, 200)
        opened = self.client.post(
            "/v1/support/requests",
            headers=self.headers("visit-token"),
            json={"subject": "Ajuda com o perfil", "content": "Preciso de orientação"},
        )
        self.assertEqual(opened.status_code, 201, opened.text)
        conversation_id = opened.json()["conversation"]["conversation_id"]
        self.assertEqual(opened.json()["conversation"]["counterpart"]["uid"], "support")

        inbox = self.client.get(
            "/v1/support/requests",
            headers=self.headers("support-token"),
        )
        self.assertEqual(inbox.status_code, 200, inbox.text)
        self.assertEqual(inbox.json()["conversations"][0]["unread_count"], 1)
        self.assertNotIn("support-uid", str(inbox.json()))
        self.assertNotIn("support-uid@example.test", str(inbox.json()))

        opened_by_support = self.client.get(
            f"/v1/support/requests/{conversation_id}",
            headers=self.headers("support-token"),
        )
        self.assertEqual(opened_by_support.status_code, 200, opened_by_support.text)
        self.assertEqual(opened_by_support.json()["conversation"]["unread_count"], 0)
        inbox_after_read = self.client.get(
            "/v1/support/requests",
            headers=self.headers("support-token"),
        )
        self.assertEqual(inbox_after_read.json()["conversations"][0]["unread_count"], 0)

        reply = self.client.post(
            f"/v1/support/requests/{conversation_id}/messages",
            headers=self.headers("support-token"),
            json={"content": "Vamos ajudar você"},
        )
        self.assertEqual(reply.status_code, 201, reply.text)
        self.assertEqual(reply.json()["sender"]["uid"], "support")
        self.assertEqual(reply.json()["sender"]["display_name"], "Suporte LiberRotas")

        requester_view = self.client.get(
            f"/v1/messages/conversations/{conversation_id}",
            headers=self.headers("visit-token"),
        )
        self.assertEqual(requester_view.status_code, 200, requester_view.text)
        self.assertEqual(requester_view.json()["messages"][-1]["sender"]["uid"], "support")
        self.assertNotIn("support-uid", str(requester_view.json()))

        resolved = self.client.post(
            f"/v1/support/requests/{conversation_id}/resolve",
            headers=self.headers("support-token"),
        )
        self.assertEqual(resolved.status_code, 200, resolved.text)
        self.assertEqual(resolved.json()["status"], "RESOLVED")
        self.assertFalse(resolved.json()["can_message"])

        final_request = self.client.post(
            f"/v1/messages/conversations/{conversation_id}/messages",
            headers=self.headers("visit-token"),
            json={"content": "Nova dúvida no chamado encerrado"},
        )
        self.assertEqual(final_request.status_code, 409, final_request.text)
        self.assertEqual(final_request.json()["code"], "CONVERSATION_CLOSED")

        denied = self.client.get(
            "/v1/support/requests",
            headers=self.headers("admin-token"),
        )
        self.assertEqual(denied.status_code, 403, denied.text)

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
