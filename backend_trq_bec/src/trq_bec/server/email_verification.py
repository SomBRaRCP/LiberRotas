"""Provisionamento público restrito e envio da verificação de e-mail."""

from __future__ import annotations

import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from html import escape
from pathlib import Path
from typing import Protocol

from firebase_admin import auth

from .config import ServerSettings


logger = logging.getLogger(__name__)
PUBLIC_ROLES = frozenset({"entrepreneur", "visitor"})
PROTECTED_ROLES = frozenset({"admin", "support", "security", "institution"})


class PublicIdentityProvisioningError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PublicIdentity:
    firebase_uid: str
    email: str
    email_verified: bool
    role: str


class PublicIdentityProvisioner(Protocol):
    def provision(self, uid: str, role: str) -> PublicIdentity: ...


class FirebasePublicIdentityProvisioner:
    """Permite ao titular escolher somente visitante ou empreendedor."""

    def provision(self, uid: str, role: str) -> PublicIdentity:
        if role not in PUBLIC_ROLES:
            raise PublicIdentityProvisioningError("PUBLIC_ROLE_INVALID")
        try:
            user = auth.get_user(uid)
        except auth.UserNotFoundError as exc:
            raise PublicIdentityProvisioningError("PUBLIC_IDENTITY_NOT_FOUND") from exc
        except Exception as exc:
            raise PublicIdentityProvisioningError("PUBLIC_IDENTITY_LOOKUP_FAILED") from exc

        if user.disabled:
            raise PublicIdentityProvisioningError("PUBLIC_IDENTITY_DISABLED")
        if not user.email:
            raise PublicIdentityProvisioningError("PUBLIC_IDENTITY_EMAIL_REQUIRED")

        claims = dict(user.custom_claims or {})
        current_role = claims.get("role")
        if claims.get("admin") is True or current_role in PROTECTED_ROLES:
            raise PublicIdentityProvisioningError("PUBLIC_ROLE_PROTECTED")
        if current_role in PUBLIC_ROLES and current_role != role:
            raise PublicIdentityProvisioningError("PUBLIC_ROLE_CONFLICT")
        if current_role not in PUBLIC_ROLES and current_role is not None:
            raise PublicIdentityProvisioningError("PUBLIC_ROLE_CONFLICT")

        claims["role"] = role
        claims["admin"] = False
        try:
            auth.set_custom_user_claims(uid, claims)
        except Exception as exc:
            raise PublicIdentityProvisioningError("PUBLIC_CLAIM_UPDATE_FAILED") from exc

        return PublicIdentity(
            firebase_uid=uid,
            email=user.email,
            email_verified=bool(user.email_verified),
            role=role,
        )


class EmailVerificationSender(Protocol):
    def send(self, uid: str, expected_email: str) -> str: ...
    def send_password_setup(self, uid: str, expected_email: str) -> str: ...


class SmtpEmailVerificationSender:
    """Gera o link no Firebase Admin e o entrega pelo SMTP autenticado."""

    def __init__(self, settings: ServerSettings) -> None:
        self.settings = settings

    def _configuration(self) -> tuple[str, str] | None:
        if not all(
            (
                self.settings.smtp_host,
                self.settings.email_from,
                self.settings.smtp_username,
                self.settings.smtp_password_path,
            )
        ):
            return None
        path = Path(self.settings.smtp_password_path)
        if not path.is_file():
            return None
        password = path.read_text(encoding="utf-8").rstrip("\r\n")
        if not password:
            return None
        return self.settings.email_from, password

    def _deliver(self, message: EmailMessage) -> str:
        try:
            configured = self._configuration()
        except (OSError, UnicodeError):
            logger.warning("Nao foi possivel ler o segredo SMTP")
            return "NOT_CONFIGURED"
        if configured is None:
            return "NOT_CONFIGURED"
        sender, password = configured
        message["From"] = sender

        try:
            if self.settings.smtp_ssl:
                smtp = smtplib.SMTP_SSL(
                    self.settings.smtp_host,
                    self.settings.smtp_port,
                    timeout=self.settings.smtp_timeout_seconds,
                    context=ssl.create_default_context(),
                )
            else:
                smtp = smtplib.SMTP(
                    self.settings.smtp_host,
                    self.settings.smtp_port,
                    timeout=self.settings.smtp_timeout_seconds,
                )
            with smtp:
                smtp.ehlo()
                if self.settings.smtp_starttls:
                    smtp.starttls(context=ssl.create_default_context())
                    smtp.ehlo()
                smtp.login(self.settings.smtp_username, password)
                refused = smtp.send_message(message)
            if refused:
                logger.warning("O servidor SMTP recusou a mensagem")
                return "SMTP_REFUSED"
        except smtplib.SMTPAuthenticationError as exc:
            if exc.smtp_code == 525:
                logger.warning("O SMTP bloqueou o IP de saida")
                return "SMTP_IP_UNAUTHORIZED"
            logger.warning("O SMTP recusou a autenticacao")
            return "SMTP_AUTH_FAILED"
        except Exception:
            logger.warning("Falha ao enviar mensagem por SMTP")
            return "SMTP_FAILED"
        return "SENT"

    def send(self, uid: str, expected_email: str) -> str:
        try:
            user = auth.get_user(uid)
        except Exception:
            logger.warning("Nao foi possivel consultar o titular da verificacao de e-mail")
            return "IDENTITY_LOOKUP_FAILED"
        if user.disabled or not user.email:
            return "IDENTITY_UNAVAILABLE"
        if user.email.casefold() != expected_email.casefold():
            return "EMAIL_MISMATCH"
        if user.email_verified:
            return "ALREADY_VERIFIED"

        continue_url = f"{self.settings.public_app_url.rstrip('/')}/login?emailVerified=1"
        try:
            verification_url = auth.generate_email_verification_link(
                user.email,
                auth.ActionCodeSettings(
                    url=continue_url,
                    handle_code_in_app=False,
                ),
            )
        except Exception:
            logger.warning("Nao foi possivel gerar o link de verificacao do Firebase")
            return "LINK_GENERATION_FAILED"

        message = EmailMessage()
        message["Subject"] = "Confirme seu e-mail no LiberRotas"
        message["To"] = user.email
        message.set_content(
            "Confirme seu e-mail para concluir o cadastro no LiberRotas.\n\n"
            f"Verificar e-mail: {verification_url}\n\n"
            "Se você não criou esta conta, ignore esta mensagem."
        )
        message.add_alternative(
            "<!doctype html>"
            '<html lang="pt-BR"><body style="font-family:Arial,sans-serif;'
            'color:#13254a;line-height:1.5">'
            "<h2>Confirme seu e-mail</h2>"
            "<p>Falta somente confirmar seu endereço de e-mail para liberar "
            "sua conta pública no LiberRotas.</p>"
            '<p style="margin:28px 0">'
            f'<a href="{escape(verification_url, quote=True)}" '
            'style="background:#ff6818;color:#fff;text-decoration:none;'
            'font-weight:bold;padding:13px 22px;border-radius:8px;display:inline-block">'
            "VERIFICAR E-MAIL</a></p>"
            "<p>Se o botão não abrir, copie este endereço no navegador:<br>"
            f'<a href="{escape(verification_url, quote=True)}">'
            f"{escape(verification_url)}</a></p>"
            "<p>Se você não criou esta conta, ignore esta mensagem.</p>"
            "</body></html>",
            subtype="html",
        )

        return self._deliver(message)

    def send_password_setup(self, uid: str, expected_email: str) -> str:
        """Envia o link de definição da senha somente para a identidade recém-criada."""

        try:
            user = auth.get_user(uid)
        except Exception:
            logger.warning("Nao foi possivel consultar a instituicao do primeiro acesso")
            return "IDENTITY_LOOKUP_FAILED"
        if user.disabled or not user.email:
            return "IDENTITY_UNAVAILABLE"
        if user.email.casefold() != expected_email.casefold():
            return "EMAIL_MISMATCH"

        continue_url = f"{self.settings.public_app_url.rstrip('/')}/login?firstAccess=1"
        try:
            setup_url = auth.generate_password_reset_link(
                user.email,
                auth.ActionCodeSettings(
                    url=continue_url,
                    handle_code_in_app=False,
                ),
            )
        except Exception:
            logger.warning("Nao foi possivel gerar o link de primeiro acesso do Firebase")
            return "LINK_GENERATION_FAILED"

        message = EmailMessage()
        message["Subject"] = "Primeiro acesso da sua instituição no LiberRotas"
        message["To"] = user.email
        message.set_content(
            "A solicitação da sua instituição foi aprovada no LiberRotas.\n\n"
            f"Definir minha senha: {setup_url}\n\n"
            "Este link é pessoal. Se você não solicitou este acesso, não abra o link e procure o Suporte."
        )
        message.add_alternative(
            "<!doctype html>"
            '<html lang="pt-BR"><body style="font-family:Arial,sans-serif;'
            'color:#13254a;line-height:1.5">'
            "<h2>Solicitação institucional aprovada</h2>"
            "<p>Sua instituição foi aprovada no LiberRotas. Defina uma senha "
            "pessoal para concluir o primeiro acesso.</p>"
            '<p style="margin:28px 0">'
            f'<a href="{escape(setup_url, quote=True)}" '
            'style="background:#ff6818;color:#fff;text-decoration:none;'
            'font-weight:bold;padding:13px 22px;border-radius:8px;display:inline-block">'
            "DEFINIR MINHA SENHA</a></p>"
            "<p>Se o botão não abrir, copie este endereço no navegador:<br>"
            f'<a href="{escape(setup_url, quote=True)}">{escape(setup_url)}</a></p>'
            "<p>Este link é pessoal. Se você não solicitou este acesso, "
            "não abra o link e procure o Suporte.</p>"
            "</body></html>",
            subtype="html",
        )
        return self._deliver(message)
