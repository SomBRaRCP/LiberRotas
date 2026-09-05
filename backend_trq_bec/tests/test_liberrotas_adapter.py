from __future__ import annotations

import base64
import time
import unittest

from trq_bec.application import build_lab_gateway
from trq_bec.contracts import Decision, Intent, Observation
from trq_bec.errors import ContractError
from trq_bec.integrations import LiberRotasBackendAdapter


class LiberRotasAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.gateway = build_lab_gateway()
        self.device_key_id = "device:liberrotas-test"
        self.gateway.create_device_key(self.device_key_id)

        def resolve(uid: str, resource: str) -> Intent:
            return Intent(
                txn_id=f"ACCESS-{uid}",
                merchant_id="LIBERSOL",
                amount_minor=1,
                currency="BRL",
                resource_ref=resource,
                purpose="LIBERROTAS_ACCESS",
            )

        def collect(uid: str, device: str, operation: str) -> list[Observation]:
            now = int(time.time())
            pairs = [
                ("device_key_known", "true", "firebase-backend"),
                ("session_context_changed", "false", "liberrotas-app"),
                ("rate_increase", "false", "firebase-backend"),
                ("geo_velocity_high", "false", "liberrotas-app"),
                ("collector_health_ok", "true", "firebase-backend"),
            ]
            return [
                Observation(name, value, source, now, now + 30, 9_000, 9_000, f"evidence:{name}")
                for name, value, source in pairs
            ]

        self.adapter = LiberRotasBackendAdapter(self.gateway, resolve, collect)

    def test_begin_and_authorize_flow(self) -> None:
        begin = self.adapter.begin(
            verified_firebase_uid="uid-123",
            resource_ref="fair/pinhais/01",
            device_key_id=self.device_key_id,
        )
        proof_message = base64.b64decode(
            begin["proof_message_b64u"] + "=" * (-len(begin["proof_message_b64u"]) % 4),
            altchars=b"-_",
        )
        signature = self.gateway.crypto.sign(self.device_key_id, proof_message, "device-proof")
        result = self.adapter.authorize(
            verified_firebase_uid="uid-123",
            operation_id=begin["operation_id"],
            session_id=begin["session_id"],
            device_key_id=self.device_key_id,
            challenge_id=begin["challenge"]["challenge_id"],
            envelope_data=begin["envelope"],
            device_proof_b64u=self.gateway.envelopes.encode_signature(signature),
        )
        self.assertEqual(result.decision, Decision.ALLOW)

    def test_firebase_uid_binding_cannot_be_swapped(self) -> None:
        begin = self.adapter.begin(
            verified_firebase_uid="uid-123",
            resource_ref="fair/pinhais/01",
            device_key_id=self.device_key_id,
        )
        with self.assertRaises(ContractError):
            self.adapter.authorize(
                verified_firebase_uid="uid-attacker",
                operation_id=begin["operation_id"],
                session_id=begin["session_id"],
                device_key_id=self.device_key_id,
                challenge_id=begin["challenge"]["challenge_id"],
                envelope_data=begin["envelope"],
                device_proof_b64u="AA",
            )


if __name__ == "__main__":
    unittest.main()

