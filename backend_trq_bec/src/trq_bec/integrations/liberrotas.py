"""Transport-neutral backend adapter for app_LiberRotas.

Firebase token verification happens before this adapter. Client-controlled
context is never accepted as trusted observations; the backend collector builds
those observations after authentication.
"""

from __future__ import annotations

import base64
import threading
import uuid
from dataclasses import dataclass
from typing import Callable

from ..application import TRQBECGateway
from ..contracts import AuthorizationResult, CryptoEnvelope, Intent, Observation
from ..errors import ContractError
from ..protocol.envelope import device_proof_message


IntentResolver = Callable[[str, str], Intent]
ObservationCollector = Callable[[str, str, str], list[Observation]]


@dataclass(frozen=True, slots=True)
class _Pending:
    firebase_uid: str
    operation_id: str
    session_id: str
    device_key_id: str
    intent: Intent
    envelope: CryptoEnvelope
    challenge_id: str


class LiberRotasBackendAdapter:
    """Maps verified LiberRotas identities/resources onto the TRQ-BEC gateway."""

    def __init__(
        self,
        gateway: TRQBECGateway,
        intent_resolver: IntentResolver,
        observation_collector: ObservationCollector,
    ) -> None:
        self.gateway = gateway
        self.intent_resolver = intent_resolver
        self.observation_collector = observation_collector
        self._pending: dict[str, _Pending] = {}
        self._lock = threading.Lock()

    def begin(self, *, verified_firebase_uid: str, resource_ref: str, device_key_id: str) -> dict:
        if not verified_firebase_uid or not resource_ref or not device_key_id:
            raise ContractError("authenticated uid, resource and device key are required")
        intent = self.intent_resolver(verified_firebase_uid, resource_ref)
        if intent.resource_ref != resource_ref:
            raise ContractError("authoritative resource mismatch")
        envelope = self.gateway.issue_token(intent)
        operation_id = f"op:{uuid.uuid4()}"
        session_id = f"session:{uuid.uuid4()}"
        challenge = self.gateway.issue_challenge(operation_id)
        proof_bytes = device_proof_message(
            envelope,
            challenge.to_dict(),
            session_id,
            device_key_id,
        )
        pending = _Pending(
            verified_firebase_uid,
            operation_id,
            session_id,
            device_key_id,
            intent,
            envelope,
            challenge.challenge_id,
        )
        with self._lock:
            self._pending[operation_id] = pending
        return {
            "operation_id": operation_id,
            "session_id": session_id,
            "envelope": envelope.to_dict(),
            "challenge": challenge.to_dict(),
            "proof_message_b64u": base64.urlsafe_b64encode(proof_bytes).rstrip(b"=").decode("ascii"),
        }

    def authorize(
        self,
        *,
        verified_firebase_uid: str,
        operation_id: str,
        session_id: str,
        device_key_id: str,
        challenge_id: str,
        envelope_data: dict,
        device_proof_b64u: str,
        step_up_passed: bool = False,
    ) -> AuthorizationResult:
        with self._lock:
            pending = self._pending.get(operation_id)
        if pending is None:
            raise ContractError("operation is unknown or expired")
        if (
            pending.firebase_uid != verified_firebase_uid
            or pending.session_id != session_id
            or pending.device_key_id != device_key_id
            or pending.challenge_id != challenge_id
        ):
            raise ContractError("operation binding mismatch")
        envelope = CryptoEnvelope.from_dict(envelope_data)
        if envelope.to_dict() != pending.envelope.to_dict():
            raise ContractError("returned envelope differs from issued envelope")
        observations = self.observation_collector(verified_firebase_uid, device_key_id, operation_id)
        result = self.gateway.authorize(
            envelope=envelope,
            expected_intent=pending.intent,
            operation_id=operation_id,
            session_id=session_id,
            device_key_id=device_key_id,
            challenge_id=challenge_id,
            device_proof_b64u=device_proof_b64u,
            observations=observations,
            step_up_passed=step_up_passed,
        )
        if not result.idempotent:
            with self._lock:
                self._pending.pop(operation_id, None)
        return result

