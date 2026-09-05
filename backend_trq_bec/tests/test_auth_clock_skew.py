from types import SimpleNamespace
from unittest.mock import patch

from trq_bec.server.auth import (
    FIREBASE_ID_TOKEN_CLOCK_SKEW_SECONDS,
    FirebaseAuthenticator,
)


def test_firebase_verification_uses_small_clock_skew_window() -> None:
    authenticator = FirebaseAuthenticator.__new__(FirebaseAuthenticator)
    authenticator.settings = SimpleNamespace(firebase_check_revoked=True)

    with patch(
        "trq_bec.server.auth.auth.verify_id_token",
        return_value={"uid": "firebase-user", "role": "visitor"},
    ) as verify_id_token:
        principal = authenticator.verify("valid-id-token")

    assert principal.uid == "firebase-user"
    assert principal.role == "visitor"
    verify_id_token.assert_called_once_with(
        "valid-id-token",
        check_revoked=True,
        clock_skew_seconds=FIREBASE_ID_TOKEN_CLOCK_SKEW_SECONDS,
    )
    assert FIREBASE_ID_TOKEN_CLOCK_SKEW_SECONDS == 30
