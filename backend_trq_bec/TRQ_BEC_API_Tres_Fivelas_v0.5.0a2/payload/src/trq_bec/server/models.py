"""Contratos estritos de HTTP e persistência."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ApiErrorResponse(StrictModel):
    """Envelope estável de erro retornado nas fronteiras de autenticação e serviço."""

    code: str = Field(description="Código de motivo legível por máquina.", examples=["AUTH_TOKEN_INVALID"])
    message: str = Field(description="Mensagem de erro legível por pessoa ou operador.", examples=["AUTH_TOKEN_INVALID"])

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
        description="Identificador estável da aplicação para a chave local do dispositivo.",
        examples=["device:expo:feirante:01"],
    )
    public_key_b64u: str = Field(
        min_length=43,
        max_length=43,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Chave pública Ed25519 bruta codificada em Base64URL sem preenchimento (perfil de laboratório).",
        examples=["iOZAaQkSG1nU4MV5kY_IRQAxIQ1o9S87b2m3oxygTlw"],
    )
    algorithm: Literal["ED25519_LAB"] = Field(description="Algoritmo de prova do dispositivo habilitado nesta versão de laboratório.")
    storage_profile: Literal["EXPO_SECURE_STORE_LAB"] = Field(
        description="Perfil esperado de proteção local da chave privada."
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
    device_key_id: str = Field(description="Identificador da chave do dispositivo aceito pelo backend.")
    status: Literal["ENROLLED", "ALREADY_ENROLLED"] = Field(description="Resultado idempotente do cadastro.")
    key_ref: str = Field(description="Referência pseudonimizada da chave, segura para registros de auditoria.")

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
        description="Identificador comercial do cupom no catálogo FEITUR.",
        examples=["FEITUR-021"],
    )
    issuer_id: str = Field(
        min_length=1,
        max_length=128,
        description="Firebase UID do empreendedor autenticado. Deve corresponder ao sujeito do token.",
        examples=["firebase-uid-feirante-001"],
    )
    city: str = Field(
        min_length=1,
        max_length=120,
        description="Contexto de cidade vinculado à intenção do cupom.",
        examples=["Pinhais - PR"],
    )
    device_key_id: str = Field(
        min_length=12,
        max_length=160,
        description="Chave do dispositivo emissor previamente cadastrada.",
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
        description="Discriminador do contrato compacto de QR do cupom.",
    )
    v: Literal[1] = Field(default=1, description="Versão do contrato de QR.")
    token_ref: str = Field(
        min_length=22,
        max_length=128,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Referência opaca do token no servidor; o envelope assinado não é exposto no QR.",
        examples=["y2Q33r5Tgpiz7ibyWkFI9L7tt-Xah6un"],
    )
    issuer_ref: str = Field(
        min_length=1,
        max_length=160,
        description="Referência pseudonimizada do emissor vinculada ao token.",
        examples=["issuer:4f1c5f4a93f2"],
    )
    expires_at: int = Field(
        description="Expiração do token em tempo Unix, em segundos.",
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
    qr_payload: CompactQrPayload = Field(description="Payload compacto para codificação no QR do cupom.")
    expires_at: int = Field(description="Expiração do envelope em tempo Unix, em segundos.", examples=[1783811490])

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
    qr_payload: CompactQrPayload = Field(description="Payload de QR produzido pelo endpoint de emissão.")
    device_key_id: str = Field(
        min_length=12,
        max_length=160,
        description="Chave do dispositivo de resgate previamente cadastrada.",
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
    challenge_id: str = Field(description="Identificador do desafio de frescor de uso único.", examples=["challenge:8d74f40a-70f0-4aa1-ae42-ef6749b6020e"])
    expires_at: int = Field(description="Expiração do desafio em tempo Unix, em segundos.", examples=[1783811445])


class BeginRedemptionResponse(StrictModel):
    operation_id: str = Field(description="Identificador estável da operação de resgate.", examples=["op:eea2915b-8783-4c98-9766-39df9c5fcf2e"])
    session_id: str = Field(description="Identificador da sessão vinculado ao desafio e ao dispositivo.", examples=["session:9d9f36e2-69ac-433d-a168-e4a4af1365ac"])
    challenge: ChallengeResponse
    proof_message_b64u: str = Field(
        description="Bytes exatos da mensagem, codificados em Base64URL sem preenchimento, que o dispositivo deve assinar.",
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
        description="Identificador da operação retornado pela etapa de início.",
        examples=["op:eea2915b-8783-4c98-9766-39df9c5fcf2e"],
    )
    session_id: str = Field(
        min_length=8,
        max_length=160,
        description="Identificador da sessão retornado pela etapa de início.",
        examples=["session:9d9f36e2-69ac-433d-a168-e4a4af1365ac"],
    )
    challenge_id: str = Field(
        min_length=16,
        max_length=160,
        description="Identificador do desafio de uso único retornado pela etapa de início.",
        examples=["challenge:8d74f40a-70f0-4aa1-ae42-ef6749b6020e"],
    )
    device_key_id: str = Field(
        min_length=12,
        max_length=160,
        description="Chave do dispositivo de resgate vinculada à operação.",
        examples=["device:expo:visitante:01"],
    )
    device_proof_b64u: str = Field(
        min_length=86,
        max_length=88,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Assinatura Ed25519 sobre `proof_message_b64u`, codificada em Base64URL sem preenchimento.",
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
        description="Decisão determinística de autorização."
    )
    operation_id: str = Field(description="Identificador da operação de resgate.")
    crypto_ok: bool = Field(description="Indica se todos os gates criptográficos obrigatórios foram aprovados.")
    reason_codes: list[str] = Field(description="Motivos legíveis por máquina que sustentam a decisão.")
    coupon_id: str | None = Field(default=None, description="Cupom liberado somente quando a política permite sua exposição.")
    event_ref: str | None = Field(default=None, description="Referência do evento no ledger append-only.")
    idempotent: bool = Field(default=False, description="Verdadeiro quando se trata de repetição segura de uma operação já concluída.")

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
    status: Literal["ok", "degraded"] = Field(description="Estado geral da infraestrutura.")
    database: bool = Field(description="Conectividade com PostgreSQL.")
    redis: bool = Field(description="Conectividade com Redis.")
    crypto_provider: str = Field(description="Provider ativo ou estado explícito de laboratório com PQ bloqueado.")
    pqc_ready: bool = Field(description="Verdadeiro somente quando o provider PQC aprovado está pronto e passou pelo autoteste.")

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
    provider: str = Field(description="Nome da implementação do provider.", examples=["UNAVAILABLE"])
    version: str = Field(description="Versão da implementação do provider.", examples=["0"])
    approved: bool = Field(description="Estado explícito de aprovação administrativa.", examples=[False])
    self_test_passed: bool = Field(description="Resultado do autoteste do provider na inicialização.", examples=[False])
    ml_kem_768: bool = Field(description="Disponibilidade de ML-KEM-768.", examples=[False])
    ml_dsa_65: bool = Field(description="Disponibilidade de ML-DSA-65.", examples=[False])
    ready: bool = Field(description="Prontidão agregada do provider usada pelos gates fail-closed.", examples=[False])

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
    first_seq: int = Field(description="Primeira sequência do ledger incluída no checkpoint.", examples=[1])
    last_seq: int = Field(description="Última sequência do ledger incluída no checkpoint.", examples=[128])
    root_hash: str = Field(description="Hash do último evento da cadeia append-only coberta.", examples=["6fb9c64085cbd1e2234916f2ab6ad37c3de9a9d2c731e6052ee742c67358ee2a"])
    policy_version: str = Field(description="Versão de política vinculada ao checkpoint assinado.", examples=["liberrotas-policy-1"])
    checkpoint_id: str = Field(description="UUID do checkpoint.", examples=["574cfa87-0c9b-4f0c-9ee0-719ee5c06f80"])
    signature_b64u: str = Field(description="Assinatura do checkpoint codificada em Base64URL sem preenchimento.", examples=["K7vQnUi9x5xJjK0KruPz3XFGVyw4Hn8lF0GZwp5nVxFA3x7TQ9kZgD0tUnqLUc7G_BFQxw3V7v7aDzc9t5LjCg"])

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
