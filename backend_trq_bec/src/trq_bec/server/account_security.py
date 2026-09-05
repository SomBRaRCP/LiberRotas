"""Alertas de novo aparelho e revogacao de sessoes da conta."""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from html import escape
from pathlib import Path
from typing import Callable, Protocol

from firebase_admin import auth

from .config import ServerSettings
from .models import DeviceRecord


logger = logging.getLogger(__name__)


class DeviceSecurityEmailNotifier(Protocol):
    def send_new_device_approval(
        self,
        uid: str,
        device: DeviceRecord,
        approval_token: str,
        ttl_seconds: int,
    ) -> str: ...


class AccountSessionRevoker(Protocol):
    def revoke_all(self, uid: str) -> None: ...


class FirebaseAccountSessionRevoker:
    """Invalida refresh tokens pelo UID obtido do ID token verificado."""

    def revoke_all(self, uid: str) -> None:
        auth.revoke_refresh_tokens(uid)


class SmtpDeviceSecurityEmailNotifier:
    """Envia alerta sem receber e-mail, UID ou URL do cliente HTTP."""

    def __init__(
        self,
        settings: ServerSettings,
        *,
        email_resolver: Callable[[str], str | None] | None = None,
    ) -> None:
        self.settings = settings
        self.email_resolver = email_resolver or self._firebase_email

    @staticmethod
    def _firebase_email(uid: str) -> str | None:
        user = auth.get_user(uid)
        if user.disabled:
            return None
        return user.email

    def _configuration(self) -> tuple[str, str] | None:
        # O LiberRotas usa SMTP autenticado. Uma configuração incompleta fica
        # desativada para nunca tentar um relay anônimo.
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

    def send_new_device_approval(
        self,
        uid: str,
        device: DeviceRecord,
        approval_token: str,
        ttl_seconds: int,
    ) -> str:
        # O token permanece no contrato interno durante a transição para não
        # quebrar clientes antigos, mas nunca entra no novo e-mail de alerta.
        del approval_token
        try:
            configured = self._configuration()
        except (OSError, UnicodeError):
            logger.warning("Nao foi possivel ler o segredo SMTP do alerta de seguranca")
            return "FAILED"
        if configured is None:
            return "NOT_CONFIGURED"

        sender, password = configured
        try:
            recipient = self.email_resolver(uid)
        except Exception:
            logger.warning("Nao foi possivel resolver o e-mail registrado no Firebase")
            return "FAILED"
        if not recipient:
            return "FAILED"

        raw_device_label = device.device_name or device.model_name or "Novo dispositivo"
        device_label = " ".join(raw_device_label.split()).strip() or "Novo dispositivo"
        devices_url = f"{self.settings.public_app_url.rstrip('/')}/account/devices"
        has_cooldown = ttl_seconds > 0
        ttl_minutes = max(1, ttl_seconds // 60) if has_cooldown else 0
        release_notice_plain = (
            f"Por segurança, ele será liberado automaticamente após {ttl_minutes} "
            "minutos de espera.\n\n"
            if has_cooldown
            else "Como esta é uma conta de visitante, o aparelho foi liberado "
            "imediatamente. Este e-mail é apenas um alerta de segurança.\n\n"
        )
        release_notice_html = (
            f"<p>Por segurança, ele será liberado automaticamente após "
            f"<strong>{ttl_minutes} minutos</strong> de espera.</p>"
            if has_cooldown
            else "<p>Como esta é uma conta de visitante, o aparelho foi liberado "
            "imediatamente. Este e-mail é apenas um alerta de segurança.</p>"
        )
        message = EmailMessage()
        message["Subject"] = "Alerta: novo dispositivo na sua conta LiberRotas"
        message["From"] = sender
        message["To"] = recipient
        message.set_content(
            "Um novo dispositivo foi conectado à sua conta LiberRotas.\n\n"
            f"{release_notice_plain}"
            "Se foi você, desconsidere esta mensagem.\n\n"
            "Se não reconhece este acesso, use o link 'Não fui eu!' abaixo, "
            "revise os dispositivos conectados e altere sua senha. Ao alterar "
            "a senha, todos os dispositivos serão desconectados.\n\n"
            f"Dispositivo: {device_label}\n"
            f"Plataforma: {device.platform}\n"
            f"Não fui eu!: {devices_url}\n"
        )
        message.add_alternative(
            "<!doctype html>"
            '<html lang="pt-BR"><body style="font-family:Arial,sans-serif;'
            'color:#13254a;line-height:1.5">'
            "<h2>Novo dispositivo conectado</h2>"
            "<p>Um novo dispositivo foi conectado à sua conta LiberRotas.</p>"
            f"{release_notice_html}"
            "<p><strong>Se foi você, desconsidere esta mensagem.</strong></p>"
            "<p>Se não reconhece este acesso, revise os dispositivos conectados "
            "e altere sua senha. A troca de senha desconecta todos os aparelhos.</p>"
            f"<p><strong>Dispositivo:</strong> {escape(device_label)}<br>"
            f"<strong>Plataforma:</strong> {escape(device.platform)}</p>"
            '<p style="margin:28px 0">'
            f'<a href="{escape(devices_url, quote=True)}" '
            'style="background:#bf241c;color:#fff;text-decoration:none;'
            'font-weight:bold;padding:13px 22px;border-radius:8px;display:inline-block">'
            "NÃO FUI EU!</a></p>"
            "<p>Se o botão não abrir, acesse:<br>"
            f'<a href="{escape(devices_url, quote=True)}">'
            f"{escape(devices_url)}</a></p>"
            "</body></html>",
            subtype="html",
        )

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
                logger.warning("O servidor SMTP recusou o alerta de seguranca")
                return "FAILED"
        except Exception:
            # O cadastro do aparelho ja foi persistido como pendente. A falha
            # de infraestrutura nunca transforma o alerta em bloqueio de login.
            logger.warning("Falha ao enviar alerta de seguranca por SMTP")
            return "FAILED"
        return "SENT"
