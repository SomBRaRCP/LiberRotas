from __future__ import annotations

import unittest

from trq_bec.canonical import encode
from trq_bec.contracts import CryptoEnvelope, Intent
from trq_bec.errors import ContractError


class CanonicalContractTests(unittest.TestCase):
    def test_canonical_order_is_deterministic(self) -> None:
        self.assertEqual(encode({"b": 2, "a": 1}), encode({"a": 1, "b": 2}))
        self.assertEqual(encode({"b": 2, "a": 1}), b'{"a":1,"b":2}')

    def test_float_is_forbidden(self) -> None:
        with self.assertRaises(ContractError):
            encode({"amount": 28.90})

    def test_money_is_positive_integer_minor_unit(self) -> None:
        with self.assertRaises(ContractError):
            Intent("t", "m", 0, "BRL", "r", "p")
        with self.assertRaises(ContractError):
            Intent("t", "m", True, "BRL", "r", "p")

    def test_unknown_envelope_field_fails_closed(self) -> None:
        data = {
            "v": 1,
            "suite_id": "s",
            "key_id": "k",
            "policy_version": "p",
            "iss": "i",
            "aud": "a",
            "purpose": "x",
            "iat": 1,
            "exp": 2,
            "jti": "0" * 32,
            "intent_digest": "0" * 64,
            "signature": "x",
            "algorithm": "none",
        }
        with self.assertRaises(ContractError):
            CryptoEnvelope.from_dict(data)


if __name__ == "__main__":
    unittest.main()

