from __future__ import annotations

import smtplib
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from trq_bec.server.account_security import SmtpDeviceSecurityEmailNotifier
from trq_bec.server.config import ServerSettings
from trq_bec.server.email_verification import SmtpEmailVerificationSender
from trq_bec.server.models import DeviceRecord


class AccountSecurityInfrastructureTests(unittest.TestCase):
    @staticmethod
    def device() -> DeviceRecord:
        now = datetime.now(timezone.utc)
        return DeviceRecord(
            firebase_uid="user-1",
            device_key_id="device:test:additional",
            public_key_b64u="A" * 43,
            algorithm="ED25519_LAB",
            storage_profile="WEB_CRYPTO_INDEXEDDB_LAB",
            status="PENDING_APPROVAL",
            device_name="Chrome\nnao vira cabecalho",
            platform="web",
            notification_status="PENDING",
            created_at=now,
            last_seen_at=now,
            approval_expires_at=now,
        )

    @staticmethod
    def smtp_settings(password_path: Path, **overrides: object) -> ServerSettings:
        values: dict[str, object] = {
            "environment": "test",
            "smtp_host": "smtp.example.test",
            "smtp_port": 2525,
            "smtp_username": "smtp-user",
            "smtp_password_path": password_path,
            "smtp_starttls": False,
            "smtp_ssl": False,
            "email_from": "security@example.test",
            "public_app_url": "https://app.liberrotas.com.br",
        }
        values.update(overrides)
        return ServerSettings(**values)

    def test_smtp_sent_is_reported_only_after_server_accepts_message(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            password_path = Path(directory) / "smtp-password"
            password_path.write_text("test-secret", encoding="utf-8")
            notifier = SmtpDeviceSecurityEmailNotifier(
                self.smtp_settings(password_path),
                email_resolver=lambda uid: "registered@example.test",
            )
            smtp = Mock()
            smtp.__enter__ = Mock(return_value=smtp)
            smtp.__exit__ = Mock(return_value=False)
            smtp.send_message.return_value = {}
            with patch("trq_bec.server.account_security.smtplib.SMTP", return_value=smtp):
                result = notifier.send_new_device_approval(
                    "user-1",
                    self.device(),
                    "A" * 43,
                    600,
                )

            self.assertEqual(result, "SENT")
            smtp.login.assert_called_once_with("smtp-user", "test-secret")
            message = smtp.send_message.call_args.args[0]
            plain_body = message.get_body(preferencelist=("plain",)).get_content()
            html_body = message.get_body(preferencelist=("html",)).get_content()
            self.assertIn("após 10 minutos", plain_body)
            self.assertIn("Não fui eu!", plain_body)
            self.assertIn(
                "https://app.liberrotas.com.br/account/devices",
                plain_body,
            )
            self.assertIn("NÃO FUI EU!", html_body)
            self.assertNotIn("approval_token", plain_body)
            self.assertNotIn("approval_token", html_body)
            self.assertNotIn("A" * 43, message.as_string())
            self.assertIn("Chrome nao vira cabecalho", plain_body)
            self.assertEqual(message["To"], "registered@example.test")

    def test_smtp_password_preserves_spaces_and_removes_only_final_newlines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            password_path = Path(directory) / "smtp-password"
            password_path.write_text(" secret-with-spaces \r\n", encoding="utf-8")
            notifier = SmtpDeviceSecurityEmailNotifier(
                self.smtp_settings(password_path),
                email_resolver=lambda uid: "registered@example.test",
            )
            smtp = Mock()
            smtp.__enter__ = Mock(return_value=smtp)
            smtp.__exit__ = Mock(return_value=False)
            smtp.send_message.return_value = {}
            with patch("trq_bec.server.account_security.smtplib.SMTP", return_value=smtp):
                result = notifier.send_new_device_approval(
                    "user-1", self.device(), "B" * 43, 1800
                )

            self.assertEqual(result, "SENT")
            smtp.login.assert_called_once_with("smtp-user", " secret-with-spaces ")

    def test_visitor_alert_reports_immediate_release_without_cooldown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            password_path = Path(directory) / "smtp-password"
            password_path.write_text("test-secret", encoding="utf-8")
            notifier = SmtpDeviceSecurityEmailNotifier(
                self.smtp_settings(password_path),
                email_resolver=lambda uid: "visitor@example.test",
            )
            smtp = Mock()
            smtp.__enter__ = Mock(return_value=smtp)
            smtp.__exit__ = Mock(return_value=False)
            smtp.send_message.return_value = {}
            with patch("trq_bec.server.account_security.smtplib.SMTP", return_value=smtp):
                result = notifier.send_new_device_approval(
                    "visitor-1",
                    self.device(),
                    "V" * 43,
                    0,
                )

            self.assertEqual(result, "SENT")
            message = smtp.send_message.call_args.args[0]
            plain_body = message.get_body(preferencelist=("plain",)).get_content()
            self.assertIn("conta de visitante", plain_body)
            self.assertIn("liberado imediatamente", plain_body)
            self.assertNotIn("minutos de espera", plain_body)

    def test_smtp_refusal_or_exception_is_failed_never_sent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            password_path = Path(directory) / "smtp-password"
            password_path.write_text("test-secret", encoding="utf-8")
            notifier = SmtpDeviceSecurityEmailNotifier(
                self.smtp_settings(password_path),
                email_resolver=lambda uid: "registered@example.test",
            )
            for side_effect, refused in (
                (None, {"registered@example.test": (550, b"rejected")}),
                (ConnectionError("offline"), None),
            ):
                with self.subTest(side_effect=side_effect):
                    smtp = Mock()
                    smtp.__enter__ = Mock(return_value=smtp)
                    smtp.__exit__ = Mock(return_value=False)
                    smtp.send_message.side_effect = side_effect
                    smtp.send_message.return_value = refused
                    with patch(
                        "trq_bec.server.account_security.smtplib.SMTP",
                        return_value=smtp,
                    ):
                        result = notifier.send_new_device_approval(
                            "user-1", self.device(), "C" * 43, 1800
                        )
                    self.assertEqual(result, "FAILED")

    def test_partial_or_missing_smtp_configuration_is_not_configured(self) -> None:
        resolver = Mock(return_value="registered@example.test")
        cases = (
            ServerSettings(environment="test"),
            ServerSettings(
                environment="test",
                smtp_host="smtp.example.test",
                email_from="security@example.test",
            ),
        )
        for settings in cases:
            with self.subTest(settings=settings):
                notifier = SmtpDeviceSecurityEmailNotifier(settings, email_resolver=resolver)
                result = notifier.send_new_device_approval(
                    "user-1", self.device(), "D" * 43, 1800
                )
                self.assertEqual(result, "NOT_CONFIGURED")
        resolver.assert_not_called()

    def test_secret_is_not_exposed_when_smtp_login_fails(self) -> None:
        sentinel = "DO_NOT_LEAK_SMTP_SECRET"
        with tempfile.TemporaryDirectory() as directory:
            password_path = Path(directory) / "smtp-password"
            password_path.write_text(sentinel, encoding="utf-8")
            notifier = SmtpDeviceSecurityEmailNotifier(
                self.smtp_settings(password_path),
                email_resolver=lambda uid: "registered@example.test",
            )
            smtp = Mock()
            smtp.__enter__ = Mock(return_value=smtp)
            smtp.__exit__ = Mock(return_value=False)
            smtp.login.side_effect = RuntimeError(f"failure containing {sentinel}")
            with self.assertLogs("trq_bec.server.account_security", level="WARNING") as logs:
                with patch(
                    "trq_bec.server.account_security.smtplib.SMTP",
                    return_value=smtp,
                ):
                    result = notifier.send_new_device_approval(
                        "user-1", self.device(), "E" * 43, 1800
                    )
            self.assertEqual(result, "FAILED")
            self.assertNotIn(sentinel, "\n".join(logs.output))

    def test_verification_queue_keeps_unauthorized_brevo_ip_retryable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            password_path = Path(directory) / "smtp-password"
            password_path.write_text("test-secret", encoding="utf-8")
            sender = SmtpEmailVerificationSender(
                self.smtp_settings(password_path),
            )
            smtp = Mock()
            smtp.__enter__ = Mock(return_value=smtp)
            smtp.__exit__ = Mock(return_value=False)
            smtp.login.side_effect = smtplib.SMTPAuthenticationError(
                525,
                b"Unauthorized IP address",
            )
            firebase_user = SimpleNamespace(
                disabled=False,
                email="registered@example.test",
                email_verified=False,
            )
            with (
                patch(
                    "trq_bec.server.email_verification.auth.get_user",
                    return_value=firebase_user,
                ),
                patch(
                    "trq_bec.server.email_verification.auth.generate_email_verification_link",
                    return_value="https://firebase.example.test/verify?redacted=1",
                ),
                patch(
                    "trq_bec.server.email_verification.smtplib.SMTP",
                    return_value=smtp,
                ),
            ):
                result = sender.send("user-1", "registered@example.test")

            self.assertEqual(result, "SMTP_IP_UNAUTHORIZED")

    def test_institution_first_access_uses_firebase_reset_link_and_authenticated_smtp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            password_path = Path(directory) / "smtp-password"
            password_path.write_text("test-secret", encoding="utf-8")
            sender = SmtpEmailVerificationSender(self.smtp_settings(password_path))
            smtp = Mock()
            smtp.__enter__ = Mock(return_value=smtp)
            smtp.__exit__ = Mock(return_value=False)
            smtp.send_message.return_value = {}
            firebase_user = SimpleNamespace(
                disabled=False,
                email="instituicao@example.test",
                email_verified=False,
            )
            with (
                patch(
                    "trq_bec.server.email_verification.auth.get_user",
                    return_value=firebase_user,
                ),
                patch(
                    "trq_bec.server.email_verification.auth.generate_password_reset_link",
                    return_value="https://firebase.example.test/first-access?redacted=1",
                ) as generate_link,
                patch(
                    "trq_bec.server.email_verification.smtplib.SMTP",
                    return_value=smtp,
                ),
            ):
                result = sender.send_password_setup(
                    "institution-1",
                    "instituicao@example.test",
                )

            self.assertEqual(result, "SENT")
            generate_link.assert_called_once()
            message = smtp.send_message.call_args.args[0]
            self.assertEqual(message["To"], "instituicao@example.test")
            self.assertEqual(
                message["Subject"],
                "Primeiro acesso da sua instituição no LiberRotas",
            )
            plain_body = message.get_body(preferencelist=("plain",))
            assert plain_body is not None
            self.assertIn(
                "https://firebase.example.test/first-access?redacted=1",
                plain_body.get_content(),
            )


if __name__ == "__main__":
    unittest.main()
