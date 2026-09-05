"""Append-only laboratory evidence ledger with signed checkpoints."""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from ..canonical import domain_message, sha3_hex
from ..crypto.interfaces import SigningProvider
from ..errors import LedgerError

FORBIDDEN_FRAGMENTS = {
    "secret", "private", "password", "plaintext", "seed", "signature",
    "payload", "key_id", "raw_key", "ciphertext", "prompt",
}


def _validate_sanitized(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = key.lower().replace("-", "_")
            if any(fragment in normalized for fragment in FORBIDDEN_FRAGMENTS):
                raise LedgerError(f"forbidden evidence field at {path}.{key}")
            _validate_sanitized(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _validate_sanitized(item, f"{path}[{index}]")


@dataclass(frozen=True, slots=True)
class LedgerEvent:
    event_id: str
    seq: int
    wall_ts: int
    mono_ns: int
    operation_id: str
    suite_id: str
    key_ref_token: str
    event_type: str
    result: str
    reason_codes: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    prev_hash: str
    event_hash: str

    def body_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "seq": self.seq,
            "wall_ts": self.wall_ts,
            "mono_ns": self.mono_ns,
            "operation_id": self.operation_id,
            "suite_id": self.suite_id,
            "key_ref_token": self.key_ref_token,
            "event_type": self.event_type,
            "result": self.result,
            "reason_codes": list(self.reason_codes),
            "evidence_refs": list(self.evidence_refs),
            "prev_hash": self.prev_hash,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.body_dict(), "event_hash": self.event_hash}


class EvidenceLedger:
    def __init__(self, path: Path | None = None, clock=time.time) -> None:
        self.path = path
        self.clock = clock
        self._events: list[LedgerEvent] = []
        self._lock = threading.Lock()
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def events(self) -> tuple[LedgerEvent, ...]:
        with self._lock:
            return tuple(self._events)

    def append(
        self,
        *,
        operation_id: str,
        suite_id: str,
        key_ref_token: str,
        event_type: str,
        result: str,
        reason_codes: tuple[str, ...] = (),
        evidence_refs: tuple[str, ...] = (),
    ) -> LedgerEvent:
        raw = {
            "operation_id": operation_id,
            "suite_id": suite_id,
            "key_ref_token": key_ref_token,
            "event_type": event_type,
            "result": result,
            "reason_codes": list(reason_codes),
            "evidence_refs": list(evidence_refs),
        }
        _validate_sanitized(raw)
        with self._lock:
            seq = len(self._events) + 1
            prev_hash = self._events[-1].event_hash if self._events else "0" * 64
            draft = LedgerEvent(
                event_id=f"event:{uuid.uuid4()}",
                seq=seq,
                wall_ts=int(self.clock()),
                mono_ns=time.monotonic_ns(),
                operation_id=operation_id,
                suite_id=suite_id,
                key_ref_token=key_ref_token,
                event_type=event_type,
                result=result,
                reason_codes=reason_codes,
                evidence_refs=evidence_refs,
                prev_hash=prev_hash,
                event_hash="",
            )
            event_hash = sha3_hex(draft.body_dict(), "TRQ-BEC/audit/v1")
            event = replace(draft, event_hash=event_hash)
            self._events.append(event)
            if self.path is not None:
                try:
                    with self.path.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
                        handle.flush()
                except OSError as exc:
                    self._events.pop()
                    raise LedgerError("evidence persistence failed") from exc
            return event

    def verify(self) -> bool:
        with self._lock:
            previous = "0" * 64
            for expected_seq, event in enumerate(self._events, start=1):
                if event.seq != expected_seq or event.prev_hash != previous:
                    return False
                if sha3_hex(event.body_dict(), "TRQ-BEC/audit/v1") != event.event_hash:
                    return False
                previous = event.event_hash
            return True

    def checkpoint(
        self,
        crypto: SigningProvider,
        checkpoint_key_id: str,
        policy_version: str,
    ) -> dict[str, Any]:
        with self._lock:
            if not self._events:
                raise LedgerError("cannot checkpoint an empty ledger")
            body = {
                "first_seq": self._events[0].seq,
                "last_seq": self._events[-1].seq,
                "root_hash": self._events[-1].event_hash,
                "policy_version": policy_version,
            }
        signature = crypto.sign(
            checkpoint_key_id,
            domain_message("TRQ-BEC/checkpoint/v1", body),
            "checkpoint-signing",
        )
        import base64
        return {**body, "signature_b64u": base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")}
