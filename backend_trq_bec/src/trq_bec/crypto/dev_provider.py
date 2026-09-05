"""In-memory laboratory provider.

This provider uses Ed25519 only so the protocol can be exercised end to end.
It is not the TRQ-BEC post-quantum production profile and never claims FIPS
validation. Private keys are kept behind this boundary and are not exportable.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from ..errors import CryptoError


@dataclass(slots=True)
class _KeyRecord:
    private: Ed25519PrivateKey | None
    public: Ed25519PublicKey
    purpose: str
    active: bool = True


class DevelopmentCryptoProvider:
    """Thread-safe, non-exportable in-memory signing provider for tests."""

    def __init__(self) -> None:
        self._keys: dict[str, _KeyRecord] = {}
        self._audit_key = secrets.token_bytes(32)
        self._lock = threading.RLock()

    def generate_signing_key(self, key_id: str, purpose: str) -> None:
        if not key_id or not purpose:
            raise CryptoError("KEY_METADATA_INVALID")
        with self._lock:
            if key_id in self._keys:
                raise CryptoError("KEY_ALREADY_EXISTS")
            private = Ed25519PrivateKey.generate()
            self._keys[key_id] = _KeyRecord(private, private.public_key(), purpose)

    def register_public_key(self, key_id: str, public: Ed25519PublicKey, purpose: str) -> None:
        with self._lock:
            if key_id in self._keys:
                raise CryptoError("KEY_ALREADY_EXISTS")
            self._keys[key_id] = _KeyRecord(None, public, purpose)

    def sign(self, key_id: str, message: bytes, purpose: str) -> bytes:
        with self._lock:
            record = self._require(key_id, purpose)
            if record.private is None:
                raise CryptoError("PRIVATE_KEY_UNAVAILABLE")
            return record.private.sign(message)

    def verify(self, key_id: str, message: bytes, signature: bytes, purpose: str) -> bool:
        try:
            with self._lock:
                record = self._require(key_id, purpose)
                record.public.verify(signature, message)
            return True
        except (CryptoError, InvalidSignature, ValueError, TypeError):
            return False

    def _require(self, key_id: str, purpose: str) -> _KeyRecord:
        record = self._keys.get(key_id)
        if record is None or not record.active or record.purpose != purpose:
            raise CryptoError("KEY_NOT_ACTIVE_FOR_PURPOSE")
        return record

    def is_active(self, key_id: str, purpose: str) -> bool:
        with self._lock:
            try:
                self._require(key_id, purpose)
                return True
            except CryptoError:
                return False

    def revoke(self, key_id: str) -> None:
        with self._lock:
            record = self._keys.get(key_id)
            if record is None:
                raise CryptoError("KEY_NOT_FOUND")
            record.active = False

    def key_ref_token(self, key_id: str) -> str:
        return self.pseudonymize("kref", key_id)

    def pseudonymize(self, namespace: str, value: str) -> str:
        digest = hmac.new(
            self._audit_key,
            f"{namespace}\x00{value}".encode("utf-8"),
            hashlib.sha3_256,
        ).hexdigest()
        return f"{namespace[:8]}:{digest}"
