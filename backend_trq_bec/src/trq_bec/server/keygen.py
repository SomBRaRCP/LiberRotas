"""Generate lab issuer/checkpoint keys and a dedicated audit HMAC key."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _write_private(path: Path, key: Ed25519PrivateKey) -> None:
    data = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)


def _write_secret(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate TRQ-BEC laboratory backend keys")
    parser.add_argument("--output", type=Path, default=Path("secrets"))
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True, mode=0o700)
    _write_private(args.output / "issuer-ed25519.pem", Ed25519PrivateKey.generate())
    _write_private(args.output / "checkpoint-ed25519.pem", Ed25519PrivateKey.generate())
    _write_secret(args.output / "audit-hmac.key", os.urandom(32))
    print("Created issuer-ed25519.pem, checkpoint-ed25519.pem, and audit-hmac.key")


if __name__ == "__main__":
    main()
