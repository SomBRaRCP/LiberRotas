"""Atomic anti-replay contract and laboratory implementation."""

from __future__ import annotations

import threading
from dataclasses import dataclass

from ..contracts import ReplayStatus


@dataclass(slots=True)
class _Reservation:
    operation_id: str
    committed: bool = False


class InMemoryReplayStore:
    """Correct within one process; replace with shared atomic storage in deployment."""

    def __init__(self) -> None:
        self._items: dict[tuple[str, str], _Reservation] = {}
        self._lock = threading.Lock()

    def reserve(self, issuer: str, jti: str, operation_id: str) -> ReplayStatus:
        key = (issuer, jti)
        with self._lock:
            current = self._items.get(key)
            if current is None:
                self._items[key] = _Reservation(operation_id)
                return ReplayStatus.NEW
            if current.operation_id == operation_id:
                return ReplayStatus.SAME_OP
            return ReplayStatus.REPLAY

    def commit(self, issuer: str, jti: str, operation_id: str) -> bool:
        with self._lock:
            current = self._items.get((issuer, jti))
            if current is None or current.operation_id != operation_id:
                return False
            if current.committed:
                return True
            current.committed = True
            return True

    def abort(self, issuer: str, jti: str, operation_id: str) -> None:
        with self._lock:
            current = self._items.get((issuer, jti))
            if current and current.operation_id == operation_id and not current.committed:
                del self._items[(issuer, jti)]

    def committed_count(self, issuer: str, jti: str) -> int:
        with self._lock:
            item = self._items.get((issuer, jti))
            return int(bool(item and item.committed))

