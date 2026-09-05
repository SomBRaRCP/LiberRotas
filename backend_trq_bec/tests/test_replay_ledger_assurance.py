from __future__ import annotations

import threading
import unittest
from dataclasses import replace

from trq_bec.assurance import AssuranceObserver
from trq_bec.contracts import ReplayStatus
from trq_bec.crypto import PQ_SUITE_ID, SuiteRegistry
from trq_bec.errors import CryptoError
from trq_bec.protocol import InMemoryReplayStore

from helpers import observations, prepared_flow
from test_gateway_security import authorize


class ReplayLedgerAssuranceTests(unittest.TestCase):
    def test_concurrent_replay_reservation_has_one_winner(self) -> None:
        store = InMemoryReplayStore()
        statuses: list[ReplayStatus] = []
        lock = threading.Lock()

        def worker(index: int) -> None:
            status = store.reserve("issuer", "jti", f"op:{index}")
            with lock:
                statuses.append(status)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(32)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(statuses.count(ReplayStatus.NEW), 1)
        self.assertEqual(statuses.count(ReplayStatus.REPLAY), 31)

    def test_ledger_detects_internal_tamper(self) -> None:
        flow = prepared_flow()
        authorize(flow)
        ledger = flow[0].ledger
        self.assertTrue(ledger.verify())
        ledger._events[0] = replace(ledger._events[0], result="ALLOW-TAMPERED")
        self.assertFalse(ledger.verify())

    def test_ledger_uses_pseudonymous_key_reference(self) -> None:
        flow = prepared_flow()
        authorize(flow)
        event = flow[0].ledger.events[0]
        self.assertTrue(event.key_ref_token.startswith("kref:"))
        self.assertNotIn(flow[3].key_id, str(event.to_dict()))

    def test_checkpoint_is_produced_without_exposing_key(self) -> None:
        flow = prepared_flow()
        authorize(flow)
        checkpoint = flow[0].ledger.checkpoint(
            flow[0].crypto, "checkpoint-lab-2026-01", flow[0].policy.policy.version
        )
        self.assertEqual(checkpoint["last_seq"], 1)
        self.assertEqual(len(checkpoint["root_hash"]), 64)
        self.assertNotIn("key", checkpoint)

    def test_ai_assurance_has_no_execution_capability(self) -> None:
        observer = AssuranceObserver()
        self.assertFalse(hasattr(observer, "crypto"))
        self.assertFalse(hasattr(observer, "policy"))
        self.assertFalse(hasattr(observer, "execute"))
        flow = prepared_flow()
        result = authorize(flow, obs=observations("high"))
        self.assertIn(result.recommendation.proposed_action, {"OBSERVE", "STEP_UP", "HOLD", "REVIEW", "PLAN_ROTATION"})

    def test_pq_suite_is_declared_but_unavailable(self) -> None:
        registry = SuiteRegistry({PQ_SUITE_ID})
        with self.assertRaisesRegex(CryptoError, "SUITE_PROVIDER_UNAVAILABLE"):
            registry.require(PQ_SUITE_ID)


if __name__ == "__main__":
    unittest.main()

