"""Interfaces that keep protocol logic independent from key material."""

from __future__ import annotations

from typing import Protocol


class SigningProvider(Protocol):
    def generate_signing_key(self, key_id: str, purpose: str) -> None: ...

    def sign(self, key_id: str, message: bytes, purpose: str) -> bytes: ...

    def verify(self, key_id: str, message: bytes, signature: bytes, purpose: str) -> bool: ...

    def key_ref_token(self, key_id: str) -> str: ...

    def revoke(self, key_id: str) -> None: ...

    def is_active(self, key_id: str, purpose: str) -> bool: ...

