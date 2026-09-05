"""Single-use verifier challenge (TRQ pulse) with atomic consumption."""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Challenge:
    challenge_id: str
    random_128: str
    issued_at: int
    expires_at: int
    operation_id: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "challenge_id": self.challenge_id,
            "random_128": self.random_128,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "operation_id": self.operation_id,
        }


class ChallengeStore:
    def __init__(self, clock=time.time) -> None:
        self._clock = clock
        self._open: dict[str, Challenge] = {}
        self._lock = threading.Lock()

    def issue(self, operation_id: str, ttl_seconds: int = 30) -> Challenge:
        now = int(self._clock())
        challenge = Challenge(secrets.token_hex(16), secrets.token_hex(16), now, now + ttl_seconds, operation_id)
        with self._lock:
            self._open[challenge.challenge_id] = challenge
        return challenge

    def peek(self, challenge_id: str, operation_id: str) -> Challenge | None:
        with self._lock:
            challenge = self._open.get(challenge_id)
            if challenge is None or challenge.operation_id != operation_id:
                return None
            if int(self._clock()) > challenge.expires_at:
                del self._open[challenge_id]
                return None
            return challenge

    def consume(self, challenge_id: str, operation_id: str) -> bool:
        with self._lock:
            challenge = self._open.get(challenge_id)
            if challenge is None or challenge.operation_id != operation_id:
                return False
            if int(self._clock()) > challenge.expires_at:
                del self._open[challenge_id]
                return False
            del self._open[challenge_id]
            return True

