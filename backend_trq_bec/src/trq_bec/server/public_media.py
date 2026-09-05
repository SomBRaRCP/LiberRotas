"""Leitura publica de midia isolada do servico comercial principal."""

from __future__ import annotations

from typing import Protocol

from .media_storage import MediaStorageError, StorageProvider
from .models import MediaAssetRecord, MediaVariantRecord
from .store import DurableStore


PUBLIC_MEDIA_ROLES = {
    "avatar",
    "entrepreneur_logo",
    "institution_logo",
    "product_image",
    "post_image",
    "fair_cover",
}

MEDIA_ROLE_ENTITY = {
    "avatar": "user",
    "entrepreneur_logo": "entrepreneur",
    "institution_logo": "institution",
    "product_image": "product",
    "post_image": "post",
    "fair_cover": "fair",
}


class PublicMediaError(RuntimeError):
    def __init__(self, code: str, status_code: int) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class PublicMediaRepository(Protocol):
    def get_asset(self, media_id: str) -> MediaAssetRecord | None: ...

    def get_asset_with_variant(
        self,
        media_id: str,
        variant: str,
    ) -> tuple[MediaAssetRecord | None, MediaVariantRecord | None]: ...

    def get_latest_ready_for_entity(
        self,
        entity_type: str,
        entity_id: str,
        media_role: str,
        variant: str,
    ) -> tuple[MediaAssetRecord | None, MediaVariantRecord | None]: ...


class DurableStorePublicMediaRepository:
    """Adaptador fino: o restante do backend ainda pode usar DurableStore."""

    def __init__(self, store: DurableStore) -> None:
        self.store = store

    def get_asset(self, media_id: str) -> MediaAssetRecord | None:
        return self.store.get_media_asset(media_id)

    def get_asset_with_variant(
        self,
        media_id: str,
        variant: str,
    ) -> tuple[MediaAssetRecord | None, MediaVariantRecord | None]:
        return self.store.get_media_asset_with_variant(media_id, variant)

    def get_latest_ready_for_entity(
        self,
        entity_type: str,
        entity_id: str,
        media_role: str,
        variant: str,
    ) -> tuple[MediaAssetRecord | None, MediaVariantRecord | None]:
        return self.store.get_latest_ready_media_for_entity(
            entity_type,
            entity_id,
            media_role,
            variant,
        )


class PublicMediaReadService:
    """Seleciona somente objetos publicos, aprovados e ja processados."""

    def __init__(
        self,
        repository: PublicMediaRepository,
        storage: StorageProvider,
        download_expiration_seconds: int,
    ) -> None:
        self.repository = repository
        self.storage = storage
        self.download_expiration_seconds = download_expiration_seconds

    @staticmethod
    def _is_public(record: MediaAssetRecord | None) -> bool:
        return bool(
            record is not None
            and record.status == "ready"
            and record.visibility == "public_processed"
            and record.moderation_status == "approved"
            and record.media_role in PUBLIC_MEDIA_ROLES
        )

    def _signed_url(self, object_key: str) -> str:
        try:
            return self.storage.create_download_url(
                object_key,
                self.download_expiration_seconds,
            )
        except MediaStorageError as exc:
            raise PublicMediaError(exc.code, 503) from exc

    def resolve_asset(self, media_id: str, variant: str | None = None) -> str:
        selected_variant = None
        if variant in {"thumbnail", "display"}:
            record, selected_variant = self.repository.get_asset_with_variant(
                media_id,
                variant,
            )
        else:
            record = self.repository.get_asset(media_id)
        if not self._is_public(record):
            raise PublicMediaError("MEDIA_ASSET_NOT_FOUND", 404)
        assert record is not None
        object_key = selected_variant.object_key if selected_variant else record.object_key
        return self._signed_url(object_key)

    def resolve_entity(
        self,
        entity_type: str,
        entity_id: str,
        media_role: str,
        variant: str,
    ) -> str:
        if (
            MEDIA_ROLE_ENTITY.get(media_role) != entity_type
            or media_role not in PUBLIC_MEDIA_ROLES
        ):
            raise PublicMediaError("MEDIA_ASSET_NOT_FOUND", 404)
        record, selected_variant = self.repository.get_latest_ready_for_entity(
            entity_type,
            entity_id,
            media_role,
            variant,
        )
        if not self._is_public(record) or selected_variant is None:
            raise PublicMediaError("MEDIA_ASSET_NOT_FOUND", 404)
        return self._signed_url(selected_variant.object_key)
