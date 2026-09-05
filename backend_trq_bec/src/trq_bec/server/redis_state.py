"""Distributed freshness, replay, idempotency, and rate signals.

Redis mutations use Lua so multiple API workers observe one atomic state.
PostgreSQL remains the durable source of truth for redeemed coupons.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any, Protocol

import redis

from ..contracts import ReplayStatus


RESERVE_REPLAY_LUA = """
local operation_id = redis.call('HGET', KEYS[1], 'operation_id')
if not operation_id then
  redis.call('HSET', KEYS[1], 'operation_id', ARGV[1], 'status', 'RESERVED')
  redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]))
  return 'NEW'
end
if operation_id == ARGV[1] then
  return 'SAME_OP'
end
return 'REPLAY'
"""

COMMIT_REPLAY_LUA = """
local operation_id = redis.call('HGET', KEYS[1], 'operation_id')
if not operation_id or operation_id ~= ARGV[1] then
  return 0
end
redis.call('HSET', KEYS[1], 'status', 'COMMITTED', 'result_json', ARGV[2])
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]))
return 1
"""

ABORT_REPLAY_LUA = """
local operation_id = redis.call('HGET', KEYS[1], 'operation_id')
local status = redis.call('HGET', KEYS[1], 'status')
if operation_id == ARGV[1] and status == 'RESERVED' then
  return redis.call('DEL', KEYS[1])
end
return 0
"""

CONSUME_CHALLENGE_LUA = """
local operation_id = redis.call('HGET', KEYS[1], 'operation_id')
if operation_id == ARGV[1] then
  redis.call('DEL', KEYS[1])
  return 1
end
return 0
"""

ISSUE_CHALLENGE_LUA = """
if redis.call('EXISTS', KEYS[1]) == 1 then
  return 0
end
redis.call('HSET', KEYS[1],
  'challenge_id', ARGV[1],
  'random_128', ARGV[2],
  'issued_at', ARGV[3],
  'expires_at', ARGV[4],
  'operation_id', ARGV[5])
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[6]))
return 1
"""

RATE_LUA = """
local value = redis.call('INCR', KEYS[1])
if value == 1 then
  redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1]))
end
return value
"""


class DistributedState(Protocol):
    def ping(self) -> bool: ...
    def issue_challenge(self, operation_id: str, ttl_seconds: int) -> dict[str, str | int]: ...
    def get_challenge(self, challenge_id: str, operation_id: str) -> dict[str, str | int] | None: ...
    def consume_challenge(self, challenge_id: str, operation_id: str) -> bool: ...
    def reserve_replay(self, issuer: str, jti: str, operation_id: str, ttl_seconds: int) -> ReplayStatus: ...
    def get_replay_result(self, issuer: str, jti: str, operation_id: str) -> dict[str, Any] | None: ...
    def commit_replay(self, issuer: str, jti: str, operation_id: str, result: dict[str, Any], ttl_seconds: int) -> bool: ...
    def abort_replay(self, issuer: str, jti: str, operation_id: str) -> None: ...
    def rate_is_high(self, subject_ref: str, window_seconds: int, threshold: int) -> bool: ...


def _digest_key(*parts: str) -> str:
    digest = hashlib.sha3_256("\x00".join(parts).encode("utf-8")).hexdigest()
    return digest


class RedisDistributedState:
    def __init__(self, url: str, *, client=None) -> None:
        self.client = client or redis.Redis.from_url(url, decode_responses=True, health_check_interval=30)

    def ping(self) -> bool:
        return bool(self.client.ping())

    def issue_challenge(self, operation_id: str, ttl_seconds: int) -> dict[str, str | int]:
        now = int(time.time())
        for _ in range(3):
            challenge = {
                "challenge_id": secrets.token_urlsafe(24),
                "random_128": secrets.token_hex(16),
                "issued_at": now,
                "expires_at": now + ttl_seconds,
                "operation_id": operation_id,
            }
            key = f"trqbec:challenge:{challenge['challenge_id']}"
            created = self.client.eval(
                ISSUE_CHALLENGE_LUA,
                1,
                key,
                challenge["challenge_id"],
                challenge["random_128"],
                challenge["issued_at"],
                challenge["expires_at"],
                operation_id,
                ttl_seconds,
            )
            if created:
                return challenge
        raise RuntimeError("CHALLENGE_ID_COLLISION")

    def get_challenge(self, challenge_id: str, operation_id: str) -> dict[str, str | int] | None:
        values = self.client.hgetall(f"trqbec:challenge:{challenge_id}")
        if not values or values.get("operation_id") != operation_id:
            return None
        try:
            expires_at = int(values["expires_at"])
            issued_at = int(values["issued_at"])
        except (KeyError, ValueError):
            return None
        if int(time.time()) > expires_at:
            return None
        return {
            "challenge_id": challenge_id,
            "random_128": values["random_128"],
            "issued_at": issued_at,
            "expires_at": expires_at,
            "operation_id": operation_id,
        }

    def consume_challenge(self, challenge_id: str, operation_id: str) -> bool:
        key = f"trqbec:challenge:{challenge_id}"
        return bool(self.client.eval(CONSUME_CHALLENGE_LUA, 1, key, operation_id))

    def _replay_key(self, issuer: str, jti: str) -> str:
        return f"trqbec:replay:{_digest_key(issuer, jti)}"

    def reserve_replay(self, issuer: str, jti: str, operation_id: str, ttl_seconds: int) -> ReplayStatus:
        result = self.client.eval(
            RESERVE_REPLAY_LUA,
            1,
            self._replay_key(issuer, jti),
            operation_id,
            ttl_seconds,
        )
        return ReplayStatus(str(result))

    def get_replay_result(self, issuer: str, jti: str, operation_id: str) -> dict[str, Any] | None:
        values = self.client.hgetall(self._replay_key(issuer, jti))
        if values.get("operation_id") != operation_id or values.get("status") != "COMMITTED":
            return None
        try:
            result = json.loads(values["result_json"])
        except (KeyError, json.JSONDecodeError):
            return None
        return result if isinstance(result, dict) else None

    def commit_replay(self, issuer: str, jti: str, operation_id: str, result: dict[str, Any], ttl_seconds: int) -> bool:
        compact = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return bool(
            self.client.eval(
                COMMIT_REPLAY_LUA,
                1,
                self._replay_key(issuer, jti),
                operation_id,
                compact,
                ttl_seconds,
            )
        )

    def abort_replay(self, issuer: str, jti: str, operation_id: str) -> None:
        self.client.eval(ABORT_REPLAY_LUA, 1, self._replay_key(issuer, jti), operation_id)

    def rate_is_high(self, subject_ref: str, window_seconds: int, threshold: int) -> bool:
        bucket = int(time.time()) // window_seconds
        key = f"trqbec:rate:{_digest_key(subject_ref, str(bucket))}"
        count = int(self.client.eval(RATE_LUA, 1, key, window_seconds + 2))
        return count > threshold


@dataclass(slots=True)
class _MemoryReplay:
    operation_id: str
    status: str
    expires_at: float
    result: dict[str, Any] | None = None


class MemoryDistributedState:
    """Deterministic test double; never selected by production configuration."""

    def __init__(self) -> None:
        self._challenges: dict[str, dict[str, str | int]] = {}
        self._replays: dict[str, _MemoryReplay] = {}
        self._rates: dict[str, tuple[int, float]] = {}
        self._lock = threading.RLock()

    def ping(self) -> bool:
        return True

    def issue_challenge(self, operation_id: str, ttl_seconds: int) -> dict[str, str | int]:
        now = int(time.time())
        challenge = {
            "challenge_id": secrets.token_urlsafe(24),
            "random_128": secrets.token_hex(16),
            "issued_at": now,
            "expires_at": now + ttl_seconds,
            "operation_id": operation_id,
        }
        with self._lock:
            self._challenges[str(challenge["challenge_id"])] = challenge
        return challenge

    def get_challenge(self, challenge_id: str, operation_id: str) -> dict[str, str | int] | None:
        with self._lock:
            item = self._challenges.get(challenge_id)
            if not item or item["operation_id"] != operation_id or int(time.time()) > int(item["expires_at"]):
                return None
            return dict(item)

    def consume_challenge(self, challenge_id: str, operation_id: str) -> bool:
        with self._lock:
            item = self.get_challenge(challenge_id, operation_id)
            if item is None:
                return False
            del self._challenges[challenge_id]
            return True

    def _replay_key(self, issuer: str, jti: str) -> str:
        return _digest_key(issuer, jti)

    def reserve_replay(self, issuer: str, jti: str, operation_id: str, ttl_seconds: int) -> ReplayStatus:
        key = self._replay_key(issuer, jti)
        now = time.time()
        with self._lock:
            current = self._replays.get(key)
            if current is None or current.expires_at <= now:
                self._replays[key] = _MemoryReplay(operation_id, "RESERVED", now + ttl_seconds)
                return ReplayStatus.NEW
            return ReplayStatus.SAME_OP if current.operation_id == operation_id else ReplayStatus.REPLAY

    def get_replay_result(self, issuer: str, jti: str, operation_id: str) -> dict[str, Any] | None:
        with self._lock:
            current = self._replays.get(self._replay_key(issuer, jti))
            if current and current.operation_id == operation_id and current.status == "COMMITTED":
                return dict(current.result or {})
            return None

    def commit_replay(self, issuer: str, jti: str, operation_id: str, result: dict[str, Any], ttl_seconds: int) -> bool:
        with self._lock:
            current = self._replays.get(self._replay_key(issuer, jti))
            if current is None or current.operation_id != operation_id:
                return False
            current.status = "COMMITTED"
            current.result = dict(result)
            current.expires_at = time.time() + ttl_seconds
            return True

    def abort_replay(self, issuer: str, jti: str, operation_id: str) -> None:
        with self._lock:
            key = self._replay_key(issuer, jti)
            current = self._replays.get(key)
            if current and current.operation_id == operation_id and current.status == "RESERVED":
                del self._replays[key]

    def rate_is_high(self, subject_ref: str, window_seconds: int, threshold: int) -> bool:
        now = time.time()
        key = _digest_key(subject_ref, str(int(now) // window_seconds))
        with self._lock:
            count, expires = self._rates.get(key, (0, now + window_seconds))
            if expires <= now:
                count, expires = 0, now + window_seconds
            count += 1
            self._rates[key] = (count, expires)
            return count > threshold
