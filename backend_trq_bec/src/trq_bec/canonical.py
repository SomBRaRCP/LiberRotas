"""Strict canonical encoding for the accepted laboratory domain.

This is deliberately smaller than a general JSON canonicalization standard:
signed contracts accept only null, booleans, integers, UTF-8 strings, lists,
and objects with string keys. Floating point values and raw bytes are rejected.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from .errors import ContractError


def _validate(value: Any, path: str = "$") -> None:
    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float):
        raise ContractError(f"floating point value forbidden at {path}")
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise ContractError(f"raw bytes forbidden at {path}; encode explicitly")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ContractError(f"non-string object key at {path}")
            _validate(item, f"{path}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            _validate(item, f"{path}[{index}]")
        return
    raise ContractError(f"unsupported canonical type {type(value).__name__} at {path}")


def encode(value: Any) -> bytes:
    """Encode an accepted value deterministically as UTF-8 JSON."""
    _validate(value)
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ContractError("canonical encoding failed") from exc


def domain_message(domain: str, value: Any) -> bytes:
    """Bind bytes to an explicit domain using an unambiguous length prefix."""
    if not domain or not domain.isascii():
        raise ContractError("domain must be non-empty ASCII")
    domain_bytes = domain.encode("ascii")
    payload = encode(value)
    return len(domain_bytes).to_bytes(2, "big") + domain_bytes + len(payload).to_bytes(8, "big") + payload


def sha3_hex(value: Any, domain: str) -> str:
    return hashlib.sha3_256(domain_message(domain, value)).hexdigest()

