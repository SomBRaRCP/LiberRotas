from __future__ import annotations

import threading
import unittest

try:
    import fakeredis
except ImportError:  # serviço real/fakeredis não está disponível em todo ambiente de teste
    fakeredis = None

from trq_bec.contracts import ReplayStatus
from trq_bec.server.redis_state import RedisDistributedState


@unittest.skipIf(fakeredis is None, "fakeredis[lua] não instalado")
class RedisLuaStateTests(unittest.TestCase):
    def setUp(self) -> None:
        client = fakeredis.FakeRedis(decode_responses=True)
        self.state = RedisDistributedState("redis://unused", client=client)

    def test_challenge_is_consumed_once(self) -> None:
        challenge = self.state.issue_challenge("op:one", 30)
        challenge_id = str(challenge["challenge_id"])
        self.assertIsNotNone(self.state.get_challenge(challenge_id, "op:one"))
        self.assertTrue(self.state.consume_challenge(challenge_id, "op:one"))
        self.assertFalse(self.state.consume_challenge(challenge_id, "op:one"))

    def test_lua_replay_reservation_has_one_winner(self) -> None:
        results: list[ReplayStatus] = []
        lock = threading.Lock()

        def reserve(index: int) -> None:
            result = self.state.reserve_replay("issuer", "shared-jti", f"op:{index}", 120)
            with lock:
                results.append(result)

        threads = [threading.Thread(target=reserve, args=(index,)) for index in range(24)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(results.count(ReplayStatus.NEW), 1)
        self.assertEqual(results.count(ReplayStatus.REPLAY), 23)

    def test_committed_result_is_idempotent(self) -> None:
        self.assertEqual(self.state.reserve_replay("issuer", "jti", "op:1", 120), ReplayStatus.NEW)
        result = {"decision": "ALLOW", "operation_id": "op:1"}
        self.assertTrue(self.state.commit_replay("issuer", "jti", "op:1", result, 120))
        self.assertEqual(self.state.reserve_replay("issuer", "jti", "op:1", 120), ReplayStatus.SAME_OP)
        self.assertEqual(self.state.get_replay_result("issuer", "jti", "op:1"), result)


if __name__ == "__main__":
    unittest.main()
