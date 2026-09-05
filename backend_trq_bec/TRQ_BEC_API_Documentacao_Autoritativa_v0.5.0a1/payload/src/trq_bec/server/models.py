"""Strict HTTP and persistence contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ApiErrorResponse(StrictModel):
    """Stable error envelope returned by authentication and service boundaries."""

    code: str = Field(description="Machine-readable reason code.", examples=["AUTH_TOKEN_INVALID"])
    message: str = Field(description="Human- or operator-readable error message.", examples=["AUTH_TOKEN_INVALID"])

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "code": "AUTH_TOKEN_INVALID",
                    "message": "AUTH_TOKEN_INVALID",
                }
            ]
        }
    )


class EnrollDeviceRequest(StrictModel):
    device_key_id: str = Field(
        min_length=12,
        max_length=160,
        pattern=r"^device:[A-Za-z0-9:_-]+$",
        description="Stable application identifier for the local device key.",
        examples=["device:expo:feirante:01"],
    )
    public_key_b64u: str = Field(
        min_length=43,
        max_length=43,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Raw Ed25519 public key encoded as unpadded Base64URL (laboratory profile).",
        examples=["iOZAaQkSG1nU4MV5kY_IRQAxIQ1o9S87b2m3oxygTlw"],
    )
    algorithm: Literal["ED25519_LAB"] = Field(description="Device-proof algorithm enabled in this laboratory version.")
    storage_profile: Literal["EXPO_SECURE_STORE_LAB"] = Field(
        description="Expected local protection profile for the private key."
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "device_key_id": "device:expo:feirante:01",
                    "public_key_b64u": "iOZAaQkSG1nU4MV5kY_IRQAxIQ1o9S87b2m3oxygTlw",
                    "algorithm": "ED25519_LAB",
                    "storage_profile": "EXPO_SECURE_STORE_LAB",
                }
            ]
        }
    )


class EnrollDeviceResponse(StrictModel):
    device_key_id: str = Field(description="Device key identifier accepted by the backend.")
    status: Literal["ENROLLED", "ALREADY_ENROLLED"] = Field(description="Idempotent enrollment result.")
    key_ref: str = Field(description="Pseudonymized key reference safe for audit records.")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "device_key_id": "device:expo:feirante:01",
                    "status": "ENROLLED",
                    "key_ref": "devref:3x6vT0ph2QmN8sYk",
                }
            ]
        }
    )


class IssueCouponRequest(StrictModel):
    coupon_id: str = Field(
        pattern=r"^FEITUR-\d{3}$",
        description="Business coupon identifier in the FEITUR catalogue.",
        examples=["FEITUR-021"],
    )
    issuer_id: str = Field(
        min_length=1,
        max_length=128,
        description="Firebase UID of the authenticated entrepreneur. Must match the token subject.",
        examples=["firebase-uid-feirante-001"],
    )
    city: str = Field(
        min_length=1,
        max_length=120,
        description="City context bound to the coupon intent.",
        examples=["Pinhais - PR"],
    )
    device_key_id: str = Field(
        min_length=12,
        max_length=160,
        description="Previously enrolled issuer device key.",
        examples=["device:expo:feirante:01"],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "coupon_id": "FEITUR-021",
                    "issuer_id": "firebase-uid-feirante-001",
                    "city": "Pinhais - PR",
                    "device_key_id": "device:expo:feirante:01",
                }
            ]
        }
    )


class CompactQrPayload(StrictModel):
    type: Literal["trq-bec-coupon-v1"] = Field(
        default="trq-bec-coupon-v1",
        description="Discriminator for the compact coupon QR contract.",
    )
    v: Literal[1] = Field(default=1, description="QR contract version.")
    token_ref: str = Field(
        min_length=22,
        max_length=128,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Opaque server-side token reference; the signed envelope is not exposed in the QR code.",
        examples=["y2Q33r5Tgpiz7ibyWkFI9L7tt-Xah6un"],
    )
    issuer_ref: str = Field(
        min_length=1,
        max_length=160,
        description="Pseudonymized issuer reference bound to the token.",
        examples=["issuer:4f1c5f4a93f2"],
    )
    expires_at: int = Field(
        description="Token expiration as Unix time in seconds.",
        examples=[1783811490],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "type": "trq-bec-coupon-v1",
                    "v": 1,
                    "token_ref": "y2Q33r5Tgpiz7ibyWkFI9L7tt-Xah6un",
                    "issuer_ref": "issuer:4f1c5f4a93f2",
                    "expires_at": 1783811490,
                }
            ]
        }
    )


class IssueCouponResponse(StrictModel):
    qr_payload: CompactQrPayload = Field(description="Compact payload to encode in the coupon QR code.")
    expires_at: int = Field(description="Envelope expiration as Unix time in seconds.", examples=[1783811490])

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "qr_payload": {
                        "type": "trq-bec-coupon-v1",
                        "v": 1,
                        "token_ref": "y2Q33r5Tgpiz7ibyWkFI9L7tt-Xah6un",
                        "issuer_ref": "issuer:4f1c5f4a93f2",
                        "expires_at": 1783811490,
                    },
                    "expires_at": 1783811490,
                }
            ]
        }
    )


class BeginRedemptionRequest(StrictModel):
    qr_payload: CompactQrPayload = Field(description="QR payload produced by the issuance endpoint.")
    device_key_id: str = Field(
        min_length=12,
        max_length=160,
        description="Previously enrolled redeemer device key.",
        examples=["device:expo:visitante:01"],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "qr_payload": {
                        "type": "trq-bec-coupon-v1",
                        "v": 1,
                        "token_ref": "y2Q33r5Tgpiz7ibyWkFI9L7tt-Xah6un",
                        "issuer_ref": "issuer:4f1c5f4a93f2",
                        "expires_at": 1783811490,
                    },
                    "device_key_id": "device:expo:visitante:01",
                }
            ]
        }
    )


class ChallengeResponse(StrictModel):
    challenge_id: str = Field(description="Single-use freshness challenge identifier.", examples=["challenge:8d74f40a-70f0-4aa1-ae42-ef6749b6020e"])
    expires_at: int = Field(description="Challenge expiration as Unix time in seconds.", examples=[1783811445])


class BeginRedemptionResponse(StrictModel):
    operation_id: str = Field(description="Stable identifier for the redemption operation.", examples=["op:eea2915b-8783-4c98-9766-39df9c5fcf2e"])
    session_id: str = Field(description="Session identifier bound to the challenge and device.", examples=["session:9d9f36e2-69ac-433d-a168-e4a4af1365ac"])
    challenge: ChallengeResponse
    proof_message_b64u: str = Field(
        description="Exact message bytes, encoded as unpadded Base64URL, that the device must sign.",
        examples=["VFJRLUJFQy9kZXZpY2UtcHJvb2YvdjE6ZXhhbXBsZS1wcm9vZi1tZXNzYWdl"],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "operation_id": "op:eea2915b-8783-4c98-9766-39df9c5fcf2e",
                    "session_id": "session:9d9f36e2-69ac-433d-a168-e4a4af1365ac",
                    "challenge": {
                        "challenge_id": "challenge:8d74f40a-70f0-4aa1-ae42-ef6749b6020e",
                        "expires_at": 1783811445,
                    },
                    "proof_message_b64u": "VFJRLUJFQy9kZXZpY2UtcHJvb2YvdjE6ZXhhbXBsZS1wcm9vZi1tZXNzYWdl",
                }
            ]
        }
    )


class AuthorizeRedemptionRequest(StrictModel):
    operation_id: str = Field(
        min_length=8,
        max_length=160,
        description="Operation identifier returned by the begin step.",
        examples=["op:eea2915b-8783-4c98-9766-39df9c5fcf2e"],
    )
    session_id: str = Field(
        min_length=8,
        max_length=160,
        description="Session identifier returned by the begin step.",
        examples=["session:9d9f36e2-69ac-433d-a168-e4a4af1365ac"],
    )
    challenge_id: str = Field(
        min_length=16,
        max_length=160,
        description="Single-use challenge identifier returned by the begin step.",
        examples=["challenge:8d74f40a-70f0-4aa1-ae42-ef6749b6020e"],
    )
    device_key_id: str = Field(
        min_length=12,
        max_length=160,
        description="Redeemer device key bound to the operation.",
        examples=["device:expo:visitante:01"],
    )
    device_proof_b64u: str = Field(
        min_length=86,
        max_length=88,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Ed25519 signature over `proof_message_b64u`, encoded as unpadded Base64URL.",
        examples=["9gAbmslLvGHuEFDf8h39jnVSrzC-ns48Boo5yHpFtOuXJEh3tockZ39gAbmslLvGHuEFDf8h39jnVSrzC-ns48"],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "operation_id": "op:eea2915b-8783-4c98-9766-39df9c5fcf2e",
                    "session_id": "session:9d9f36e2-69ac-433d-a168-e4a4af1365ac",
                    "challenge_id": "challenge:8d74f40a-70f0-4aa1-ae42-ef6749b6020e",
                    "device_key_id": "device:expo:visitante:01",
                    "device_proof_b64u": "9gAbmslLvGHuEFDf8h39jnVSrzC-ns48Boo5yHpFtOuXJEh3tockZ39gAbmslLvGHuEFDf8h39jnVSrzC-ns48",
                }
            ]
        }
    )


class AuthorizationResponse(StrictModel):
    decision: Literal["DENY", "ALLOW", "STEP_UP", "HOLD_OR_REVIEW"] = Field(
        description="Deterministic authorization decision."
    )
    operation_id: str = Field(description="Redemption operation identifier.")
    crypto_ok: bool = Field(description="Whether all mandatory cryptographic gates passed.")
    reason_codes: list[str] = Field(description="Machine-readable reasons supporting the decision.")
    coupon_id: str | None = Field(default=None, description="Coupon released only when policy permits disclosure.")
    event_ref: str | None = Field(default=None, description="Append-only ledger event reference.")
    idempotent: bool = Field(default=False, description="True when this is a safe replay of an already completed operation.")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "decision": "ALLOW",
                    "operation_id": "op:eea2915b-8783-4c98-9766-39df9c5fcf2e",
                    "crypto_ok": True,
                    "reason_codes": [],
                    "coupon_id": "FEITUR-021",
                    "event_ref": "event:36cc48bf-908f-4b90-b91e-57951a97be10",
                    "idempotent": False,
                }
            ]
        }
    )


class HealthResponse(StrictModel):
    status: Literal["ok", "degraded"] = Field(description="Overall infrastructure state.")
    database: bool = Field(description="PostgreSQL connectivity.")
    redis: bool = Field(description="Redis connectivity.")
    crypto_provider: str = Field(description="Active provider, or explicit laboratory/PQ-blocked state.")
    pqc_ready: bool = Field(description="True only when the approved PQC provider is ready and self-tested.")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "ok",
                    "database": True,
                    "redis": True,
                    "crypto_provider": "LAB_ED25519_PQ_BLOCKED",
                    "pqc_ready": False,
                }
            ]
        }
    )


class CryptoHealthResponse(StrictModel):
    provider: str = Field(description="Provider implementation name.", examples=["UNAVAILABLE"])
    version: str = Field(description="Provider implementation version.", examples=["0"])
    approved: bool = Field(description="Explicit administrative approval status.", examples=[False])
    self_test_passed: bool = Field(description="Provider startup self-test result.", examples=[False])
    ml_kem_768: bool = Field(description="Availability of ML-KEM-768.", examples=[False])
    ml_dsa_65: bool = Field(description="Availability of ML-DSA-65.", examples=[False])
    ready: bool = Field(description="Aggregate provider readiness used by fail-closed gates.", examples=[False])

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "provider": "UNAVAILABLE",
                    "version": "0",
                    "approved": False,
                    "self_test_passed": False,
                    "ml_kem_768": False,
                    "ml_dsa_65": False,
                    "ready": False,
                }
            ]
        }
    )


class LedgerCheckpointResponse(StrictModel):
    first_seq: int = Field(description="First ledger sequence included in the checkpoint.", examples=[1])
    last_seq: int = Field(description="Last ledger sequence included in the checkpoint.", examples=[128])
    root_hash: str = Field(description="Hash of the last event in the covered append-only chain.", examples=["6fb9c64085cbd1e2234916f2ab6ad37c3de9a9d2c731e6052ee742c67358ee2a"])
    policy_version: str = Field(description="Policy version bound to the signed checkpoint.", examples=["liberrotas-policy-1"])
    checkpoint_id: str = Field(description="Checkpoint UUID.", examples=["574cfa87-0c9b-4f0c-9ee0-719ee5c06f80"])
    signature_b64u: str = Field(description="Checkpoint signature encoded as unpadded Base64URL.", examples=["K7vQnUi9x5xJjK0KruPz3XFGVyw4Hn8lF0GZwp5nVxFA3x7TQ9kZgD0tUnqLUc7G_BFQxw3V7v7aDzc9t5LjCg"])

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "first_seq": 1,
                    "last_seq": 128,
                    "root_hash": "6fb9c64085cbd1e2234916f2ab6ad37c3de9a9d2c731e6052ee742c67358ee2a",
                    "policy_version": "liberrotas-policy-1",
                    "checkpoint_id": "574cfa87-0c9b-4f0c-9ee0-719ee5c06f80",
                    "signature_b64u": "K7vQnUi9x5xJjK0KruPz3XFGVyw4Hn8lF0GZwp5nVxFA3x7TQ9kZgD0tUnqLUc7G_BFQxw3V7v7aDzc9t5LjCg",
                }
            ]
        }
    )


@dataclass(frozen=True, slots=True)
class Principal:
    uid: str
    role: str | None
    email: str | None
    claims: dict[str, Any]

    @property
    def is_entrepreneur(self) -> bool:
        return self.role == "entrepreneur"

    @property
    def is_admin(self) -> bool:
        return bool(self.claims.get("admin"))


@dataclass(frozen=True, slots=True)
class DeviceRecord:
    firebase_uid: str
    device_key_id: str
    public_key_b64u: str
    algorithm: str
    status: str


@dataclass(frozen=True, slots=True)
class CouponRecord:
    coupon_id: str
    owner_uid: str | None
    active: bool
    valid_until: int | None


@dataclass(frozen=True, slots=True)
class TokenRecord:
    token_ref: str
    issuer_uid: str
    issuer_ref: str
    coupon_id: str
    intent: dict[str, Any]
    envelope: dict[str, Any]
    expires_at: int
    status: str
    redeemed_operation_id: str | None


@dataclass(frozen=True, slots=True)
class OperationRecord:
    operation_id: str
    firebase_uid: str
    session_id: str
    token_ref: str
    device_key_id: str
    challenge_id: str
    expires_at: int
    status: str
    result: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class AuditRecord:
    event_id: str
    seq: int
    event_hash: str
