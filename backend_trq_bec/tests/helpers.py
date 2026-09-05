from __future__ import annotations

import time
import uuid

from trq_bec.application import build_lab_gateway
from trq_bec.contracts import Intent, Observation


def make_intent(amount_minor: int = 2890) -> Intent:
    return Intent(
        txn_id="LIBER-TEST-001",
        merchant_id="LIBERSOL-TEST",
        amount_minor=amount_minor,
        currency="BRL",
        resource_ref="route/test/001",
        purpose="LIBERROTAS_ACCESS",
    )


def observations(mode: str = "low") -> list[Observation]:
    now = int(time.time())
    values = {
        "low": ("true", "false", "false", "false", "true"),
        "high": ("true", "true", "true", "true", "true"),
    }[mode]
    names = (
        "device_key_known",
        "session_context_changed",
        "rate_increase",
        "geo_velocity_high",
        "collector_health_ok",
    )
    sources = (
        "firebase-backend",
        "liberrotas-app",
        "firebase-backend",
        "liberrotas-app",
        "firebase-backend",
    )
    return [
        Observation(name, value, source, now, now + 60, 9_500, 9_500, f"evidence:{name}")
        for name, value, source in zip(names, values, sources, strict=True)
    ]


def prepared_flow():
    gateway = build_lab_gateway()
    device_key_id = f"device:{uuid.uuid4()}"
    gateway.create_device_key(device_key_id)
    intent = make_intent()
    envelope = gateway.issue_token(intent)
    operation_id = f"op:{uuid.uuid4()}"
    session_id = f"session:{uuid.uuid4()}"
    challenge = gateway.issue_challenge(operation_id)
    proof = gateway.sign_device_proof(
        envelope,
        challenge.challenge_id,
        operation_id,
        session_id,
        device_key_id,
    )
    return gateway, device_key_id, intent, envelope, operation_id, session_id, challenge, proof

