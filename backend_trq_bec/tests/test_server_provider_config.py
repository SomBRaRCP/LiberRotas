from __future__ import annotations

import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

from trq_bec.server.config import ServerSettings
from trq_bec.server.keygen import main as keygen
from trq_bec.server.media_storage import (
    DisabledStorageProvider,
    GoogleCloudStorageProvider,
    MediaStorageDisabled,
    MediaStorageError,
    build_storage_provider,
)
from trq_bec.server.provider import FileEd25519Provider, UnavailablePQCProvider


class ServerProviderConfigTests(unittest.TestCase):
    @staticmethod
    def gcs_credentials_json(private_key: str = "PRIVATE_KEY_FOR_TEST_ONLY") -> str:
        return json.dumps(
            {
                "type": "service_account",
                "project_id": "liberrotas-media-test",
                "private_key": private_key,
                "client_email": "media-test@liberrotas-media-test.iam.gserviceaccount.com",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        )

    @staticmethod
    def production_kwargs(password_path: Path, **overrides: Any) -> dict[str, Any]:
        values: dict[str, Any] = {
            "environment": "production",
            "public_app_url": "https://app.liberrotas.com.br",
            "smtp_host": "smtp-relay.brevo.com",
            "smtp_port": 587,
            "smtp_username": "smtp-user",
            "smtp_password_path": password_path,
            "smtp_starttls": True,
            "smtp_ssl": False,
            "smtp_timeout_seconds": 10,
            "email_from": "seguranca@liberrotas.com.br",
            "firebase_credentials_path": Path("firebase.json"),
            "issuer_private_key_path": Path("issuer.pem"),
            "checkpoint_private_key_path": Path("checkpoint.pem"),
            "audit_hmac_key_path": Path("audit.key"),
            "lab_suite_enabled": False,
            "pqc_provider_approved": True,
            "firebase_check_revoked": True,
        }
        values.update(overrides)
        return values

    def test_keygen_and_file_provider_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "secrets"
            keygen(["--output", str(root)])
            provider = FileEd25519Provider(
                "issuer",
                root / "issuer-ed25519.pem",
                "checkpoint",
                root / "checkpoint-ed25519.pem",
                root / "audit-hmac.key",
            )
            message = b"TRQ-BEC provider self-test"
            signature = provider.sign("issuer", message, "token-signing")
            self.assertTrue(provider.verify("issuer", message, signature, "token-signing"))
            self.assertFalse(provider.verify("issuer", message + b"x", signature, "token-signing"))
            self.assertNotEqual(
                provider.pseudonymize("actor", "uid-1"),
                provider.pseudonymize("actor", "uid-2"),
            )

    def test_production_rejects_lab_or_missing_provider(self) -> None:
        with self.assertRaises(ValueError):
            ServerSettings(environment="production")

        with tempfile.TemporaryDirectory() as directory:
            password_path = Path(directory) / "smtp-password"
            password_path.write_text("test-secret", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "firebase_check_revoked"):
                ServerSettings(
                    **self.production_kwargs(
                        password_path,
                        firebase_check_revoked=False,
                    )
                )

    def test_future_provider_is_fail_closed(self) -> None:
        provider = UnavailablePQCProvider("future-vendor", "1.0")
        self.assertFalse(provider.status().ready)
        self.assertFalse(provider.self_test())

    def test_security_email_configuration_rejects_unsafe_combinations(self) -> None:
        with self.assertRaisesRegex(ValueError, "smtp_ssl and smtp_starttls"):
            ServerSettings(environment="test", smtp_ssl=True, smtp_starttls=True)

        with self.assertRaisesRegex(ValueError, "smtp_username and smtp_password_path"):
            ServerSettings(
                environment="test",
                smtp_host="smtp.example.test",
                email_from="security@example.test",
                smtp_username="security@example.test",
            )

    def test_blank_optional_smtp_values_are_unset(self) -> None:
        settings = ServerSettings(
            environment="development",
            smtp_host=" ",
            smtp_username="",
            smtp_password_path="",
            email_from="\t",
        )
        self.assertIsNone(settings.smtp_host)
        self.assertIsNone(settings.smtp_username)
        self.assertIsNone(settings.smtp_password_path)
        self.assertIsNone(settings.email_from)

    def test_production_rejects_placeholder_or_missing_smtp_username(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            password_path = Path(directory) / "smtp-password"
            password_path.write_text("test-secret", encoding="utf-8")
            for username in (None, "", "CHANGE_ME", "seu-usuario-brevo", "conta-smtp"):
                with self.subTest(username=username):
                    with self.assertRaisesRegex(ValueError, "SMTP username"):
                        ServerSettings(
                            **self.production_kwargs(
                                password_path,
                                smtp_username=username,
                            )
                        )

    def test_production_rejects_invalid_smtp_password_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            missing = root / "missing"
            directory_path = root / "smtp-directory"
            directory_path.mkdir()
            empty = root / "empty"
            empty.write_text("", encoding="utf-8")
            newline_only = root / "newline-only"
            newline_only.write_text("\r\n", encoding="utf-8")
            invalid_utf8 = root / "invalid-utf8"
            invalid_utf8.write_bytes(b"\xff\xfe")

            for target in (missing, directory_path, empty, newline_only, invalid_utf8):
                with self.subTest(target=target.name):
                    with self.assertRaisesRegex(ValueError, "SMTP password"):
                        ServerSettings(**self.production_kwargs(target))

    def test_production_rejects_invalid_public_application_urls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            password_path = Path(directory) / "smtp-password"
            password_path.write_text("test-secret", encoding="utf-8")
            invalid_urls = (
                "http://app.liberrotas.com.br",
                "https://localhost:8081",
                "https://localhost.",
                "https://127.0.0.1",
                "https://127.0.0.2",
                "https://[::1]",
                "https://[::ffff:127.0.0.1]",
                "https://usuario:senha@app.liberrotas.com.br",
                "https://app.liberrotas.com.br/account/devices",
                "https://app.liberrotas.com.br?next=/account/devices",
                "https://app.liberrotas.com.br?",
                "https://app.liberrotas.com.br#fragment",
                "https://app.liberrotas.com.br#",
                " https://app.liberrotas.com.br",
            )
            for public_url in invalid_urls:
                with self.subTest(public_url=public_url):
                    with self.assertRaisesRegex(ValueError, "Public application URL"):
                        ServerSettings(
                            **self.production_kwargs(
                                password_path,
                                public_app_url=public_url,
                            )
                        )

    def test_production_rejects_invalid_sender_addresses(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            password_path = Path(directory) / "smtp-password"
            password_path.write_text("test-secret", encoding="utf-8")
            for sender in (
                "security@example",
                " security@example.test",
                "security@example.test ",
                "security name@example.test",
                ".security@example.test",
                "security.@example.test",
                "secur..ity@example.test",
                "security@example.test\r\nBcc:attacker@example.test",
            ):
                with self.subTest(sender=sender):
                    with self.assertRaisesRegex(ValueError, "SMTP email sender"):
                        ServerSettings(
                            **self.production_kwargs(
                                password_path,
                                email_from=sender,
                            )
                        )

    def test_production_accepts_valid_smtp_configuration_without_exposing_secret(self) -> None:
        sentinel = "DO_NOT_LEAK_SENTINEL"
        with tempfile.TemporaryDirectory() as directory:
            password_path = Path(directory) / "smtp-password"
            password_path.write_text(f" {sentinel} \r\n", encoding="utf-8")
            settings = ServerSettings(**self.production_kwargs(password_path))
            self.assertEqual(settings.smtp_host, "smtp-relay.brevo.com")
            self.assertEqual(settings.smtp_port, 587)
            self.assertEqual(settings.email_from, "seguranca@liberrotas.com.br")
            self.assertNotIn(sentinel, repr(settings))

            with self.assertRaises(ValueError) as raised:
                ServerSettings(
                    **self.production_kwargs(
                        password_path,
                        lab_suite_enabled=True,
                    )
                )
            self.assertNotIn(sentinel, str(raised.exception))

    def test_gcs_disabled_starts_without_credentials_or_sdk_initialization(self) -> None:
        settings = ServerSettings(
            environment="test",
            gcs_enabled=False,
            gcs_project_id=None,
            gcs_bucket_name=None,
            gcs_credentials_file=None,
            gcs_credentials_json=None,
        )
        with (
            patch("trq_bec.server.media_storage.storage.Client") as client,
            patch(
                "trq_bec.server.media_storage.service_account.Credentials"
                ".from_service_account_info"
            ) as credentials,
        ):
            provider = build_storage_provider(settings)

        self.assertIsInstance(provider, DisabledStorageProvider)
        self.assertFalse(provider.enabled)
        self.assertFalse(provider.configured)
        client.assert_not_called()
        credentials.assert_not_called()
        with self.assertRaisesRegex(MediaStorageDisabled, "MEDIA_STORAGE_DISABLED"):
            provider.create_upload_url("object", "image/jpeg", "media-id", 600)

    def test_gcs_enabled_rejects_incomplete_or_invalid_credentials_without_leak(
        self,
    ) -> None:
        sentinel = "GCS_PRIVATE_KEY_DO_NOT_LEAK"
        cases = (
            (
                "missing-project",
                {
                    "gcs_enabled": True,
                    "gcs_bucket_name": "liberrotas-private-test",
                    "gcs_credentials_json": self.gcs_credentials_json(),
                },
                "GCS project ID",
            ),
            (
                "missing-bucket",
                {
                    "gcs_enabled": True,
                    "gcs_project_id": "liberrotas-media-test",
                    "gcs_credentials_json": self.gcs_credentials_json(),
                },
                "GCS bucket name",
            ),
            (
                "missing-credential-source",
                {
                    "gcs_enabled": True,
                    "gcs_project_id": "liberrotas-media-test",
                    "gcs_bucket_name": "liberrotas-private-test",
                },
                "exactly one GCS credential source",
            ),
            (
                "invalid-json",
                {
                    "gcs_enabled": True,
                    "gcs_project_id": "liberrotas-media-test",
                    "gcs_bucket_name": "liberrotas-private-test",
                    "gcs_credentials_json": f"{{invalid:{sentinel}",
                },
                "GCS credential JSON is invalid",
            ),
            (
                "incomplete-json",
                {
                    "gcs_enabled": True,
                    "gcs_project_id": "liberrotas-media-test",
                    "gcs_bucket_name": "liberrotas-private-test",
                    "gcs_credentials_json": json.dumps(
                        {
                            "type": "service_account",
                            "private_key": sentinel,
                        }
                    ),
                },
                "GCS credential JSON is invalid",
            ),
        )
        for name, values, message in cases:
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, message) as raised:
                    ServerSettings(environment="test", **values)
                self.assertNotIn(sentinel, str(raised.exception))
                self.assertNotIn(sentinel, repr(raised.exception))

        with tempfile.TemporaryDirectory() as directory:
            missing_file = Path(directory) / "missing-service-account.json"
            with self.assertRaisesRegex(
                ValueError, "GCS credential file is missing or unreadable"
            ):
                ServerSettings(
                    environment="test",
                    gcs_enabled=True,
                    gcs_project_id="liberrotas-media-test",
                    gcs_bucket_name="liberrotas-private-test",
                    gcs_credentials_file=missing_file,
                )

    def test_gcs_v4_put_url_uses_fixed_upload_contract_and_sanitizes_errors(
        self,
    ) -> None:
        sentinel = "GCS_CREDENTIAL_DO_NOT_LEAK"
        settings = ServerSettings(
            environment="test",
            gcs_enabled=True,
            gcs_project_id="liberrotas-media-test",
            gcs_bucket_name="liberrotas-private-test",
            gcs_credentials_json=self.gcs_credentials_json(sentinel),
        )
        credentials_object = object()
        client = Mock()
        bucket = Mock()
        blob = Mock()
        client.bucket.return_value = bucket
        bucket.blob.return_value = blob
        signed_url = (
            "https://storage.googleapis.test/private-object?"
            "X-Goog-Signature=TEST_SIGNATURE"
        )
        blob.generate_signed_url.return_value = signed_url

        with (
            patch(
                "trq_bec.server.media_storage.service_account.Credentials"
                ".from_service_account_info",
                return_value=credentials_object,
            ) as credentials_factory,
            patch(
                "trq_bec.server.media_storage.storage.Client",
                return_value=client,
            ) as storage_client,
        ):
            provider = GoogleCloudStorageProvider(settings)

        media_id = "123e4567-e89b-42d3-a456-426614174000"
        returned_url, headers = provider.create_upload_url(
            "media/post/opaque/image.jpg",
            "image/jpeg",
            media_id,
            321,
        )

        self.assertEqual(returned_url, signed_url)
        self.assertEqual(
            headers,
            {
                "Content-Type": "image/jpeg",
                "x-goog-meta-media-id": media_id,
            },
        )
        blob.generate_signed_url.assert_called_once_with(
            version="v4",
            expiration=timedelta(seconds=321),
            method="PUT",
            content_type="image/jpeg",
            headers={"x-goog-meta-media-id": media_id},
            query_parameters={"ifGenerationMatch": "0"},
        )
        storage_client.assert_called_once_with(
            project="liberrotas-media-test",
            credentials=credentials_object,
        )
        credentials_factory.assert_called_once()

        blob.generate_signed_url.side_effect = RuntimeError(
            f"{sentinel} {signed_url}"
        )
        with self.assertRaises(MediaStorageError) as raised:
            provider.create_upload_url(
                "media/post/opaque/image.jpg",
                "image/jpeg",
                media_id,
                321,
            )
        self.assertEqual(str(raised.exception), "MEDIA_UPLOAD_URL_FAILED")
        self.assertNotIn(sentinel, str(raised.exception))
        self.assertNotIn(signed_url, str(raised.exception))

        with patch(
            "trq_bec.server.media_storage.service_account.Credentials"
            ".from_service_account_info",
            side_effect=RuntimeError(sentinel),
        ):
            with self.assertRaises(MediaStorageError) as credential_error:
                GoogleCloudStorageProvider(settings)
        self.assertEqual(
            str(credential_error.exception),
            "MEDIA_STORAGE_CONFIGURATION_INVALID",
        )
        self.assertNotIn(sentinel, str(credential_error.exception))


if __name__ == "__main__":
    unittest.main()
