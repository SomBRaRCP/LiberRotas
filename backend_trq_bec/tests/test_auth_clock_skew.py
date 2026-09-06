from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

import firebase_admin
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from firebase_admin import credentials
from google.auth import crypt, jwt
from google.auth.credentials import AnonymousCredentials

from trq_bec.server.auth import (
    FIREBASE_ADMIN_CLOCK_SKEW_SECONDS,
    FIREBASE_ID_TOKEN_CLOCK_SKEW_SECONDS,
    FirebaseAuthenticator,
)


def test_primary_verification_respects_firebase_admin_limit() -> None:
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
        clock_skew_seconds=FIREBASE_ADMIN_CLOCK_SKEW_SECONDS,
    )
    assert FIREBASE_ADMIN_CLOCK_SKEW_SECONDS == 60
    assert FIREBASE_ID_TOKEN_CLOCK_SKEW_SECONDS == 300


PROJECT_ID = "clock-skew-test"
NOW = datetime(2026, 9, 6, 20, 0, 0, tzinfo=timezone.utc)
NOW_SECONDS = int(NOW.timestamp())


class OfflineCredential(credentials.Base):
    def get_credential(self):
        return AnonymousCredentials()


@pytest.fixture(scope="module")
def signing_key():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return crypt.RSASigner.from_string(private_pem, key_id="test-key"), public_pem


@pytest.fixture
def offline_firebase(monkeypatch, signing_key):
    # Assinatura, metadados e datas passam pelos verificadores reais. Apenas
    # relógio, certificados e consulta da conta são substituídos, sem rede.
    monkeypatch.delenv("FIREBASE_AUTH_EMULATOR_HOST", raising=False)
    app = firebase_admin.initialize_app(OfflineCredential(), {"projectId": PROJECT_ID})
    monkeypatch.setattr("google.auth._helpers.utcnow", lambda: NOW)
    fetch_certs = Mock(return_value={"test-key": signing_key[1]})
    monkeypatch.setattr("google.oauth2.id_token._fetch_certs", fetch_certs)
    user = SimpleNamespace(disabled=False, tokens_valid_after_timestamp=0)
    get_user = Mock(return_value=user)
    monkeypatch.setattr("firebase_admin._auth_client.Client.get_user", lambda self, uid: get_user(uid))
    authenticator = FirebaseAuthenticator.__new__(FirebaseAuthenticator)
    authenticator.settings = SimpleNamespace(firebase_check_revoked=True)
    yield SimpleNamespace(
        authenticator=authenticator, user=user, get_user=get_user, fetch_certs=fetch_certs
    )
    firebase_admin.delete_app(app)


def signed_token(signing_key, *, header=None, **overrides):
    claims = {
        "aud": PROJECT_ID,
        "iss": f"https://securetoken.google.com/{PROJECT_ID}",
        "sub": "existing-user",
        "iat": NOW_SECONDS + 240,
        "exp": NOW_SECONDS + 3840,
        "auth_time": NOW_SECONDS - 600,
        "role": "visitor",
    }
    claims.update(overrides)
    return jwt.encode(signing_key[0], claims, header=header).decode()


@pytest.mark.parametrize("ahead_seconds", [0, 35, 60, 61, 240, 299, 300])
def test_accepts_signed_tokens_issued_up_to_five_minutes_ahead(
    offline_firebase, signing_key, ahead_seconds
):
    principal = offline_firebase.authenticator.verify(
        signed_token(signing_key, iat=NOW_SECONDS + ahead_seconds, uid="spoofed-uid")
    )
    assert principal.uid == "existing-user"
    assert principal.role == "visitor"
    offline_firebase.get_user.assert_called_once_with("existing-user")


@pytest.mark.parametrize("expired_seconds", [60, 61, 240, 299, 300])
def test_accepts_expiration_only_within_five_minute_tolerance(
    offline_firebase, signing_key, expired_seconds
):
    principal = offline_firebase.authenticator.verify(
        signed_token(signing_key, iat=NOW_SECONDS - 3600, exp=NOW_SECONDS - expired_seconds)
    )
    assert principal.uid == "existing-user"
    offline_firebase.get_user.assert_called_once_with("existing-user")


@pytest.mark.parametrize("time_claims", [
    {"iat": NOW_SECONDS + 301},
    {"iat": NOW_SECONDS + 600},
    {"iat": NOW_SECONDS - 3600, "exp": NOW_SECONDS - 301},
    {"iat": NOW_SECONDS - 3600, "exp": NOW_SECONDS - 600},
])
def test_rejects_tokens_outside_five_minutes(offline_firebase, signing_key, time_claims):
    with pytest.raises(HTTPException) as error:
        offline_firebase.authenticator.verify(signed_token(signing_key, **time_claims))
    assert error.value.status_code == 401
    assert error.value.detail == "AUTH_TOKEN_INVALID"
    offline_firebase.get_user.assert_not_called()


@pytest.mark.parametrize("claims", [
    {"aud": "another-project"},
    {"iss": "https://securetoken.google.com/another-project"},
    {"sub": ""},
    {"sub": "x" * 129},
    {"sub": None},
    {"iat": None},
    {"exp": None},
])
def test_rejects_invalid_claims_despite_clock_tolerance(offline_firebase, signing_key, claims):
    with pytest.raises(HTTPException) as error:
        offline_firebase.authenticator.verify(signed_token(signing_key, **claims))
    assert error.value.status_code == 401
    offline_firebase.get_user.assert_not_called()


@pytest.mark.parametrize("header", [{"alg": "none"}, {"alg": "HS256"}, {"alg": "ES256"}])
def test_rejects_incorrect_algorithms(offline_firebase, signing_key, header):
    with pytest.raises(HTTPException):
        offline_firebase.authenticator.verify(signed_token(signing_key, header=header))
    offline_firebase.fetch_certs.assert_not_called()
    offline_firebase.get_user.assert_not_called()


def test_rejects_modified_signature(offline_firebase, signing_key):
    token = signed_token(signing_key)
    parts = token.split(".")
    parts[2] = ("A" if parts[2][0] != "A" else "B") + parts[2][1:]
    with pytest.raises(HTTPException):
        offline_firebase.authenticator.verify(".".join(parts))
    assert offline_firebase.fetch_certs.call_count == 1
    offline_firebase.get_user.assert_not_called()


@pytest.mark.parametrize("ahead_seconds", [35, 240])
@pytest.mark.parametrize("blocked_state", ["disabled", "revoked", "unavailable"])
def test_preserves_account_and_revocation_checks(
    offline_firebase, signing_key, ahead_seconds, blocked_state
):
    if blocked_state == "disabled":
        offline_firebase.user.disabled = True
    elif blocked_state == "revoked":
        offline_firebase.user.tokens_valid_after_timestamp = (NOW_SECONDS + ahead_seconds + 1) * 1000
    else:
        offline_firebase.get_user.side_effect = RuntimeError("account lookup unavailable")
    with pytest.raises(HTTPException) as error:
        offline_firebase.authenticator.verify(
            signed_token(signing_key, iat=NOW_SECONDS + ahead_seconds)
        )
    assert error.value.status_code == 401
    assert error.value.detail == "AUTH_TOKEN_INVALID"
    offline_firebase.get_user.assert_called_once_with("existing-user")
