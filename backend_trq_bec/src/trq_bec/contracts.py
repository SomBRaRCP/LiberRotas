"""Versioned, strict domain contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, ClassVar

from .errors import ContractError


class Decision(StrEnum):
    DENY = "DENY"
    ALLOW = "ALLOW"
    STEP_UP = "STEP_UP"
    HOLD_OR_REVIEW = "HOLD_OR_REVIEW"


class ReplayStatus(StrEnum):
    NEW = "NEW"
    SAME_OP = "SAME_OP"
    REPLAY = "REPLAY"


class ScoreKind(StrEnum):
    HEURISTIC_INDEX = "HEURISTIC_INDEX"
    CALIBRATED_PROBABILITY = "CALIBRATED_PROBABILITY"


def _strict_keys(data: dict[str, Any], allowed: set[str], required: set[str]) -> None:
    unknown = set(data) - allowed
    missing = required - set(data)
    if unknown:
        raise ContractError(f"unknown fields: {sorted(unknown)}")
    if missing:
        raise ContractError(f"missing fields: {sorted(missing)}")


def _bounded_text(name: str, value: str, maximum: int = 160) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ContractError(f"{name} must be non-empty and at most {maximum} characters")
    return value


@dataclass(frozen=True, slots=True)
class Intent:
    txn_id: str
    merchant_id: str
    amount_minor: int
    currency: str
    resource_ref: str
    purpose: str

    def __post_init__(self) -> None:
        for name in ("txn_id", "merchant_id", "resource_ref", "purpose"):
            _bounded_text(name, getattr(self, name))
        if not isinstance(self.amount_minor, int) or isinstance(self.amount_minor, bool) or self.amount_minor <= 0:
            raise ContractError("amount_minor must be a positive integer")
        if not isinstance(self.currency, str) or len(self.currency) != 3 or not self.currency.isupper():
            raise ContractError("currency must be a three-letter uppercase code")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Intent":
        keys = {"txn_id", "merchant_id", "amount_minor", "currency", "resource_ref", "purpose"}
        _strict_keys(data, keys, keys)
        return cls(**data)


@dataclass(frozen=True, slots=True)
class CryptoEnvelope:
    v: int
    suite_id: str
    key_id: str
    policy_version: str
    iss: str
    aud: str
    purpose: str
    iat: int
    exp: int
    jti: str
    intent_digest: str
    signature: str = ""

    REQUIRED: ClassVar[set[str]] = {
        "v", "suite_id", "key_id", "policy_version", "iss", "aud", "purpose",
        "iat", "exp", "jti", "intent_digest", "signature",
    }

    def __post_init__(self) -> None:
        if self.v != 1:
            raise ContractError("unsupported envelope version")
        for name in ("suite_id", "key_id", "policy_version", "iss", "aud", "purpose"):
            _bounded_text(name, getattr(self, name))
        if not all(isinstance(x, int) and not isinstance(x, bool) for x in (self.iat, self.exp)):
            raise ContractError("iat and exp must be integers")
        if self.exp <= self.iat:
            raise ContractError("exp must be after iat")
        if len(self.jti) != 32 or any(c not in "0123456789abcdef" for c in self.jti):
            raise ContractError("jti must be 128-bit lowercase hexadecimal")
        if len(self.intent_digest) != 64 or any(c not in "0123456789abcdef" for c in self.intent_digest):
            raise ContractError("intent_digest must be SHA3-256 lowercase hexadecimal")
        if self.signature and len(self.signature) > 4096:
            raise ContractError("signature exceeds maximum size")

    def unsigned_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("signature")
        return data

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CryptoEnvelope":
        if not isinstance(data, dict):
            raise ContractError("envelope must be an object")
        _strict_keys(data, cls.REQUIRED, cls.REQUIRED)
        return cls(**data)


@dataclass(frozen=True, slots=True)
class Observation:
    name: str
    value: str
    source: str
    observed_at: int
    expires_at: int
    quality_bps: int
    integrity_bps: int
    evidence_ref: str

    def __post_init__(self) -> None:
        for name in ("name", "value", "source", "evidence_ref"):
            _bounded_text(name, getattr(self, name), 256)
        if self.expires_at < self.observed_at:
            raise ContractError("observation expiry precedes observation")
        for name in ("quality_bps", "integrity_bps"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 10_000:
                raise ContractError(f"{name} must be integer basis points in [0, 10000]")


@dataclass(frozen=True, slots=True)
class RiskResult:
    event_id: str
    score_kind: ScoreKind
    risk_bps: int
    coverage_bps: int
    quality_bps: int
    reason_codes: tuple[str, ...]
    detector_version: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("risk_bps", "coverage_bps", "quality_bps"):
            value = getattr(self, name)
            if not 0 <= value <= 10_000:
                raise ContractError(f"{name} out of range")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["score_kind"] = self.score_kind.value
        return data


@dataclass(frozen=True, slots=True)
class AuditRecommendation:
    finding_id: str
    severity: str
    proposed_action: str
    reviewer_state: str
    policy_version: str
    evidence_refs: tuple[str, ...]
    reason_codes: tuple[str, ...]
    confidence_bps: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AuthorizationResult:
    decision: Decision
    operation_id: str
    crypto_ok: bool
    reason_codes: tuple[str, ...]
    risk: RiskResult | None = None
    recommendation: AuditRecommendation | None = None
    event_refs: tuple[str, ...] = field(default_factory=tuple)
    idempotent: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "operation_id": self.operation_id,
            "crypto_ok": self.crypto_ok,
            "reason_codes": list(self.reason_codes),
            "risk": self.risk.to_dict() if self.risk else None,
            "recommendation": self.recommendation.to_dict() if self.recommendation else None,
            "event_refs": list(self.event_refs),
            "idempotent": self.idempotent,
        }

