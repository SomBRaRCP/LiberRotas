"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
import time
import uuid

from .application import build_lab_gateway
from .contracts import Intent, Observation


def run_demo() -> dict:
    gateway = build_lab_gateway()
    device_key_id = "device:demo-01"
    gateway.create_device_key(device_key_id)
    intent = Intent(
        txn_id="LIBER-ROTA-0001",
        merchant_id="LIBERSOL-DEMO",
        amount_minor=2890,
        currency="BRL",
        resource_ref="route/curitiba/0001",
        purpose="LIBERROTAS_ACCESS",
    )
    envelope = gateway.issue_token(intent)
    operation_id = f"op:{uuid.uuid4()}"
    session_id = f"session:{uuid.uuid4()}"
    challenge = gateway.issue_challenge(operation_id)
    proof = gateway.sign_device_proof(
        envelope, challenge.challenge_id, operation_id, session_id, device_key_id
    )
    now = int(time.time())
    observations = [
        Observation("device_key_known", "true", "firebase-backend", now, now + 30, 10_000, 10_000, "evidence:device"),
        Observation("session_context_changed", "false", "liberrotas-app", now, now + 30, 9_500, 9_500, "evidence:session"),
        Observation("rate_increase", "false", "firebase-backend", now, now + 30, 9_000, 10_000, "evidence:rate"),
        Observation("geo_velocity_high", "false", "liberrotas-app", now, now + 30, 9_000, 9_000, "evidence:geo"),
        Observation("collector_health_ok", "true", "firebase-backend", now, now + 30, 10_000, 10_000, "evidence:health"),
    ]
    result = gateway.authorize(
        envelope=envelope,
        expected_intent=intent,
        operation_id=operation_id,
        session_id=session_id,
        device_key_id=device_key_id,
        challenge_id=challenge.challenge_id,
        device_proof_b64u=proof,
        observations=observations,
    )
    return {
        "profile": "LAB_ONLY",
        "envelope": envelope.to_dict(),
        "authorization": result.to_dict(),
        "ledger_valid": gateway.ledger.verify(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TRQ-BEC laboratory reference")
    parser.add_argument("command", choices=["demo"], help="operation to run")
    args = parser.parse_args(argv)
    if args.command == "demo":
        print(json.dumps(run_demo(), indent=2, ensure_ascii=False))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

