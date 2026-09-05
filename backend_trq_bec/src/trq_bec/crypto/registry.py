"""Signed-policy-facing cryptographic suite registry.

The post-quantum suite is intentionally unavailable in this laboratory build.
Selecting it fails closed until an audited ML-KEM/ML-DSA provider is installed.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..errors import CryptoError

LAB_SUITE_ID = "TRQ-BEC-LAB-ED25519-AES256GCM-SHA3"
PQ_SUITE_ID = "TRQ-BEC-PQ-MLKEM768-MLDSA65-AES256GCM-SHA3"


@dataclass(frozen=True, slots=True)
class CryptoSuite:
    suite_id: str
    signature: str
    kem: str | None
    aead: str
    hash_name: str
    production: bool
    available: bool


class SuiteRegistry:
    def __init__(self, allowlist: set[str] | None = None) -> None:
        self._suites = {
            LAB_SUITE_ID: CryptoSuite(
                LAB_SUITE_ID, "Ed25519", None, "AES-256-GCM", "SHA3-256", False, True
            ),
            PQ_SUITE_ID: CryptoSuite(
                PQ_SUITE_ID, "ML-DSA-65", "ML-KEM-768", "AES-256-GCM", "SHA3-256", True, False
            ),
        }
        self._allowlist = allowlist or {LAB_SUITE_ID}

    def require(self, suite_id: str) -> CryptoSuite:
        suite = self._suites.get(suite_id)
        if suite is None or suite_id not in self._allowlist:
            raise CryptoError("SUITE_NOT_ALLOWED")
        if not suite.available:
            raise CryptoError("SUITE_PROVIDER_UNAVAILABLE")
        return suite

    def describe(self) -> tuple[CryptoSuite, ...]:
        return tuple(self._suites.values())

