"""Stable key boundary plus a fail-closed future PQC provider contract."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from ..errors import CryptoError


@dataclass(frozen=True, slots=True)
class PQCProviderStatus:
    name: str
    version: str
    approved: bool
    self_test_passed: bool
    ml_kem_768: bool
    ml_dsa_65: bool

    @property
    def ready(self) -> bool:
        return self.approved and self.self_test_passed and self.ml_kem_768 and self.ml_dsa_65


class PostQuantumProvider(Protocol):
    def status(self) -> PQCProviderStatus: ...
    def self_test(self) -> bool: ...
    def ml_dsa_sign(self, key_id: str, message: bytes, context: bytes) -> bytes: ...
    def ml_dsa_verify(self, key_id: str, message: bytes, signature: bytes, context: bytes) -> bool: ...
    def ml_kem_encapsulate(self, key_id: str) -> tuple[bytes, bytes]: ...
    def ml_kem_decapsulate(self, key_id: str, ciphertext: bytes) -> bytes: ...


class UnavailablePQCProvider:
    def __init__(self, name: str = "UNAVAILABLE", version: str = "0") -> None:
        self._status = PQCProviderStatus(name, version, False, False, False, False)

    def status(self) -> PQCProviderStatus:
        return self._status

    def self_test(self) -> bool:
        return False

    def _blocked(self):
        raise CryptoError("PQC_PROVIDER_NOT_APPROVED")

    def ml_dsa_sign(self, key_id: str, message: bytes, context: bytes) -> bytes:
        return self._blocked()

    def ml_dsa_verify(self, key_id: str, message: bytes, signature: bytes, context: bytes) -> bool:
        return self._blocked()

    def ml_kem_encapsulate(self, key_id: str) -> tuple[bytes, bytes]:
        return self._blocked()

    def ml_kem_decapsulate(self, key_id: str, ciphertext: bytes) -> bytes:
        return self._blocked()


def _secure_file(path: Path) -> None:
    mode = path.stat().st_mode & 0o777
    # No Windows, ``st_mode`` não representa as ACLs do NTFS e normalmente
    # informa 0o666 mesmo para um arquivo restrito ao usuário atual. A checagem
    # POSIX continua obrigatória no Linux e dentro dos contêineres.
    if os.name != "nt" and mode & 0o077:
        raise CryptoError(f"KEY_FILE_PERMISSIONS_TOO_BROAD:{path.name}")


class FileEd25519Provider:
    """Lab signing provider loaded from root-readable secret mounts."""

    def __init__(
        self,
        issuer_key_id: str,
        issuer_path: Path,
        checkpoint_key_id: str,
        checkpoint_path: Path,
        audit_hmac_path: Path,
    ) -> None:
        for path in (issuer_path, checkpoint_path, audit_hmac_path):
            _secure_file(path)
        self._keys = {
            issuer_key_id: (self._load_private(issuer_path), "token-signing"),
            checkpoint_key_id: (self._load_private(checkpoint_path), "checkpoint-signing"),
        }
        self._active = set(self._keys)
        self._audit_hmac_key = audit_hmac_path.read_bytes()
        if len(self._audit_hmac_key) != 32:
            raise CryptoError("AUDIT_HMAC_KEY_MUST_BE_32_BYTES")

    @staticmethod
    def _load_private(path: Path) -> Ed25519PrivateKey:
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise CryptoError("SIGNING_KEY_TYPE_INVALID")
        return key

    def generate_signing_key(self, key_id: str, purpose: str) -> None:
        raise CryptoError("FILE_PROVIDER_KEYGEN_DISABLED")

    def sign(self, key_id: str, message: bytes, purpose: str) -> bytes:
        key, expected_purpose = self._require(key_id)
        if purpose != expected_purpose:
            raise CryptoError("KEY_PURPOSE_MISMATCH")
        return key.sign(message)

    def verify(self, key_id: str, message: bytes, signature: bytes, purpose: str) -> bool:
        try:
            key, expected_purpose = self._require(key_id)
            if purpose != expected_purpose:
                return False
            key.public_key().verify(signature, message)
            return True
        except (CryptoError, InvalidSignature, ValueError, TypeError):
            return False

    def _require(self, key_id: str) -> tuple[Ed25519PrivateKey, str]:
        item = self._keys.get(key_id)
        if item is None or key_id not in self._active:
            raise CryptoError("KEY_NOT_ACTIVE")
        return item

    def key_ref_token(self, key_id: str) -> str:
        return self.pseudonymize("key", key_id)

    def pseudonymize(self, namespace: str, value: str) -> str:
        digest = hmac.new(
            self._audit_hmac_key,
            f"{namespace}\x00{value}".encode("utf-8"),
            hashlib.sha3_256,
        ).hexdigest()
        return f"{namespace[:8]}:{digest}"

    def revoke(self, key_id: str) -> None:
        self._active.discard(key_id)

    def is_active(self, key_id: str, purpose: str) -> bool:
        item = self._keys.get(key_id)
        return bool(item and key_id in self._active and item[1] == purpose)


def verify_device_signature(public_key_b64u: str, message: bytes, signature_b64u: str) -> bool:
    try:
        public_raw = base64.urlsafe_b64decode(public_key_b64u + "=" * (-len(public_key_b64u) % 4))
        signature = base64.urlsafe_b64decode(signature_b64u + "=" * (-len(signature_b64u) % 4))
        if len(public_raw) != 32 or len(signature) != 64:
            return False
        Ed25519PublicKey.from_public_bytes(public_raw).verify(signature, message)
        return True
    except (ValueError, InvalidSignature, TypeError):
        return False
