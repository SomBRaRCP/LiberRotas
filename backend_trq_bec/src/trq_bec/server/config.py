"""Environment-only backend configuration with production guards."""

from __future__ import annotations

import ipaddress
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_EMAIL_RE = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)
_SMTP_USERNAME_PLACEHOLDERS = {
    "change_me",
    "seu-usuario-brevo",
    "conta-smtp",
    "example",
    "placeholder",
}
_SUPPORTED_IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
_GCS_BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,220}[a-z0-9]$")
_GCS_PROJECT_RE = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")


class ServerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="TRQ_BEC_",
        extra="ignore",
        case_sensitive=False,
    )

    environment: Literal["development", "test", "production"] = "development"
    host: str = "0.0.0.0"
    port: int = Field(default=8787, ge=1, le=65535)
    workers: int = Field(default=1, ge=1, le=32)
    log_level: str = "info"
    forwarded_allow_ips: str = "127.0.0.1"

    database_url: str = "postgresql://trq_bec:trq_bec@127.0.0.1:5432/trq_bec"
    redis_url: str = "redis://127.0.0.1:6379/0"
    database_pool_min: int = Field(default=2, ge=1, le=50)
    database_pool_max: int = Field(default=10, ge=1, le=100)

    firebase_credentials_path: Path | None = None
    firebase_project_id: str | None = None
    firebase_check_revoked: bool = True

    issuer: str = "trq-bec.liberrotas.local"
    audience: str = "app-liberrotas"
    policy_version: str = "liberrotas-policy-1"
    token_ttl_seconds: int = Field(default=90, ge=15, le=300)
    live_offer_max_ttl_seconds: int = Field(default=28_800, ge=300, le=86_400)
    challenge_ttl_seconds: int = Field(default=45, ge=10, le=120)
    device_enrollment_max_auth_age_seconds: int = Field(default=300, ge=60, le=3600)
    device_auto_activation_delay_seconds: int = Field(default=600, ge=60, le=3600)
    device_approval_ttl_seconds: int = Field(default=1800, ge=300, le=86_400)
    device_approval_resend_cooldown_seconds: int = Field(default=60, ge=30, le=3600)
    device_max_pending_per_account: int = Field(default=5, ge=1, le=20)
    replay_ttl_seconds: int = Field(default=600, ge=120, le=86_400)
    operation_ttl_seconds: int = Field(default=120, ge=30, le=600)
    rate_window_seconds: int = Field(default=60, ge=10, le=3600)
    rate_high_threshold: int = Field(default=10, ge=2, le=1000)

    issuer_private_key_path: Path | None = None
    checkpoint_private_key_path: Path | None = None
    audit_hmac_key_path: Path | None = None
    issuer_key_id: str = "issuer-lab-2026-01"
    checkpoint_key_id: str = "checkpoint-lab-2026-01"
    lab_suite_enabled: bool = True

    pqc_provider_name: str = "UNAVAILABLE"
    pqc_provider_version: str = "0"
    pqc_provider_approved: bool = False

    cors_origins: str = (
        "http://localhost:8081,http://localhost:19006,"
        "http://127.0.0.1:8082,http://localhost:8082"
    )
    docs_enabled: bool = True

    public_app_url: str = "https://app.liberrotas.com.br"
    public_api_url: str = "https://api.liberrotas.com.br"
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password_path: Path | None = None
    smtp_starttls: bool = True
    smtp_ssl: bool = False
    smtp_timeout_seconds: float = Field(default=5.0, ge=1.0, le=30.0)
    email_from: str | None = None

    gcs_enabled: bool = False
    gcs_project_id: str | None = None
    gcs_bucket_name: str | None = None
    gcs_credentials_file: Path | None = None
    gcs_credentials_json: SecretStr | None = None
    gcs_signed_url_expiration_seconds: int = Field(default=600, ge=60, le=3600)
    gcs_download_url_expiration_seconds: int = Field(default=300, ge=60, le=3600)
    gcs_upload_max_size_bytes: int = Field(default=5_242_880, ge=1024, le=52_428_800)
    gcs_public_media_base_url: str | None = None
    gcs_allowed_image_types: str = "image/jpeg,image/png,image/webp"
    media_pending_expiration_seconds: int = Field(default=86_400, ge=600, le=604_800)
    media_orphan_retention_seconds: int = Field(
        default=604_800, ge=86_400, le=2_592_000
    )
    media_max_pending_per_user: int = Field(default=10, ge=1, le=100)
    media_max_avatar_images: int = Field(default=1, ge=1, le=5)
    media_max_logo_images: int = Field(default=1, ge=1, le=5)
    media_max_product_images: int = Field(default=10, ge=1, le=50)
    media_max_post_images: int = Field(default=8, ge=1, le=20)
    media_max_fair_cover_images: int = Field(default=1, ge=1, le=5)
    media_image_max_pixels: int = Field(default=40_000_000, ge=1_000_000, le=100_000_000)
    media_image_max_dimension: int = Field(default=4096, ge=512, le=8192)

    @field_validator(
        "smtp_host",
        "smtp_username",
        "smtp_password_path",
        "email_from",
        "gcs_project_id",
        "gcs_bucket_name",
        "gcs_credentials_file",
        "gcs_credentials_json",
        "gcs_public_media_base_url",
        mode="before",
    )
    @classmethod
    def blank_optional_smtp_values_are_unset(cls, value: Any) -> Any:
        """Treat blank optional SMTP environment values as absent."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def gcs_allowed_image_type_list(self) -> tuple[str, ...]:
        return tuple(
            item.strip().lower()
            for item in self.gcs_allowed_image_types.split(",")
            if item.strip()
        )

    @staticmethod
    def _is_placeholder(value: str | None) -> bool:
        if not value:
            return True
        return value.strip().lower() in _SMTP_USERNAME_PLACEHOLDERS

    def _validate_smtp_password_file(self) -> None:
        path = self.smtp_password_path
        if path is None or not path.is_file():
            raise ValueError("SMTP password file is missing, unreadable, or empty.")
        try:
            file_content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ValueError("SMTP password file is missing, unreadable, or empty.") from exc
        if not file_content.rstrip("\r\n"):
            raise ValueError("SMTP password file is missing, unreadable, or empty.")

    @staticmethod
    def _validate_email_address(value: str | None) -> None:
        if value is None:
            raise ValueError("SMTP email sender is required in production.")
        if value != value.strip() or any(char.isspace() for char in value):
            raise ValueError("SMTP email sender is invalid.")
        if not _EMAIL_RE.fullmatch(value):
            raise ValueError("SMTP email sender is invalid.")
        local_part, _ = value.rsplit("@", 1)
        if (
            len(value) > 254
            or len(local_part) > 64
            or local_part.startswith(".")
            or local_part.endswith(".")
            or ".." in local_part
        ):
            raise ValueError("SMTP email sender is invalid.")

    @staticmethod
    def _validate_public_origin(value: str, label: str) -> None:
        if not value or value != value.strip() or any(char.isspace() for char in value):
            raise ValueError(f"{label} is invalid in production.")
        try:
            parsed = urlparse(value)
            host = parsed.hostname
            _ = parsed.port
        except ValueError as exc:
            raise ValueError(f"{label} is invalid in production.") from exc
        if parsed.scheme != "https" or not parsed.netloc or not host:
            raise ValueError(f"{label} must use HTTPS in production.")
        if parsed.username or parsed.password:
            raise ValueError(f"{label} must not contain credentials.")
        if (
            parsed.path not in {"", "/"}
            or parsed.params
            or parsed.query
            or parsed.fragment
            or "?" in value
            or "#" in value
        ):
            raise ValueError(
                f"{label} must be an HTTPS origin without path, query, or fragment."
            )

        normalized_host = host.rstrip(".").lower()
        if normalized_host == "localhost":
            raise ValueError(f"{label} must not use a local host in production.")
        try:
            address = ipaddress.ip_address(normalized_host)
        except ValueError:
            return
        mapped_loopback = (
            address.version == 6
            and address.ipv4_mapped is not None
            and address.ipv4_mapped.is_loopback
        )
        if address.is_loopback or mapped_loopback:
            raise ValueError(f"{label} must not use a local host in production.")

    def _validate_public_app_url(self) -> None:
        self._validate_public_origin(self.public_app_url, "Public application URL")

    def _validate_public_api_url(self) -> None:
        self._validate_public_origin(self.public_api_url, "Public API URL")

    def _validate_gcs_configuration(self) -> None:
        allowed_types = self.gcs_allowed_image_type_list
        if not allowed_types or len(set(allowed_types)) != len(allowed_types):
            raise ValueError("GCS allowed image types must be a non-empty unique list.")
        unsupported = sorted(set(allowed_types) - _SUPPORTED_IMAGE_TYPES)
        if unsupported:
            raise ValueError("GCS allowed image types contain an unsupported value.")
        if not self.gcs_enabled:
            return

        if not self.gcs_project_id or not _GCS_PROJECT_RE.fullmatch(self.gcs_project_id):
            raise ValueError("GCS project ID is missing or invalid.")
        if not self.gcs_bucket_name or not _GCS_BUCKET_RE.fullmatch(self.gcs_bucket_name):
            raise ValueError("GCS bucket name is missing or invalid.")
        if self.gcs_bucket_name.startswith("goog") or "google" in self.gcs_bucket_name:
            raise ValueError("GCS bucket name is not allowed.")

        configured_credentials = int(self.gcs_credentials_file is not None) + int(
            self.gcs_credentials_json is not None
        )
        if configured_credentials != 1:
            raise ValueError(
                "Configure exactly one GCS credential source: file or JSON."
            )
        if self.gcs_credentials_file is not None:
            try:
                if not self.gcs_credentials_file.is_file():
                    raise ValueError("GCS credential file is missing or unreadable.")
            except OSError as exc:
                raise ValueError("GCS credential file is missing or unreadable.") from exc
        if self.gcs_credentials_json is not None:
            try:
                document = json.loads(self.gcs_credentials_json.get_secret_value())
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError("GCS credential JSON is invalid.") from exc
            required_keys = {"type", "project_id", "private_key", "client_email", "token_uri"}
            if (
                not isinstance(document, dict)
                or document.get("type") != "service_account"
                or not required_keys.issubset(document)
            ):
                raise ValueError("GCS credential JSON is invalid.")

        if self.gcs_public_media_base_url:
            value = self.gcs_public_media_base_url
            try:
                parsed = urlparse(value)
                _ = parsed.port
            except ValueError as exc:
                raise ValueError("GCS public media base URL is invalid.") from exc
            if (
                value != value.strip()
                or any(char.isspace() for char in value)
                or parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("GCS public media base URL is invalid.")

    @model_validator(mode="after")
    def production_guards(self) -> "ServerSettings":
        if self.database_pool_min > self.database_pool_max:
            raise ValueError("database_pool_min cannot exceed database_pool_max")
        self._validate_gcs_configuration()
        if self.smtp_ssl and self.smtp_starttls:
            raise ValueError("smtp_ssl and smtp_starttls cannot both be true")
        if self.environment != "production":
            if bool(self.smtp_username) != bool(self.smtp_password_path):
                raise ValueError("smtp_username and smtp_password_path must be configured together")
            if not self.public_app_url.startswith(("https://", "http://")):
                raise ValueError("public_app_url must be an HTTP(S) URL")
            if not self.public_api_url.startswith(("https://", "http://")):
                raise ValueError("public_api_url must be an HTTP(S) URL")
            return self

        self._validate_public_app_url()
        self._validate_public_api_url()
        if self.smtp_host is None or not self.smtp_host.strip():
            raise ValueError("SMTP host is required in production.")
        if self.smtp_username is None or self._is_placeholder(self.smtp_username):
            raise ValueError(
                "SMTP username is required and cannot be a placeholder in production."
            )
        self._validate_email_address(self.email_from)
        self._validate_smtp_password_file()

        required = {
            "firebase_credentials_path": self.firebase_credentials_path,
            "issuer_private_key_path": self.issuer_private_key_path,
            "checkpoint_private_key_path": self.checkpoint_private_key_path,
            "audit_hmac_key_path": self.audit_hmac_key_path,
        }
        missing = [name for name, value in required.items() if value is None]
        if missing:
            raise ValueError(f"production configuration missing: {', '.join(missing)}")
        if self.lab_suite_enabled:
            raise ValueError("lab_suite_enabled must be false in production")
        if not self.firebase_check_revoked:
            raise ValueError("firebase_check_revoked must be true in production")
        if not self.pqc_provider_approved:
            raise ValueError("production requires an explicitly approved PQC provider")
        return self


@lru_cache(maxsize=1)
def get_settings() -> ServerSettings:
    return ServerSettings()
