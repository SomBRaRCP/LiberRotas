"""Private object-storage adapter used by the LiberRotas media service."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from google.api_core.exceptions import NotFound, PreconditionFailed
from google.cloud import storage
from google.oauth2 import service_account

from .config import ServerSettings


class MediaStorageError(RuntimeError):
    """Storage failure represented by a stable code without provider details."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class MediaStorageDisabled(MediaStorageError):
    def __init__(self) -> None:
        super().__init__("MEDIA_STORAGE_DISABLED")


class MediaObjectNotFound(MediaStorageError):
    def __init__(self) -> None:
        super().__init__("MEDIA_OBJECT_NOT_FOUND")


class MediaObjectConflict(MediaStorageError):
    def __init__(self) -> None:
        super().__init__("MEDIA_OBJECT_CONFLICT")


@dataclass(frozen=True, slots=True)
class StorageObjectMetadata:
    bucket_name: str
    object_key: str
    size_bytes: int
    content_type: str | None
    crc32c: str | None
    generation: int | None
    metadata: dict[str, str]


class StorageProvider(Protocol):
    name: str
    enabled: bool
    configured: bool

    def create_upload_url(
        self,
        object_key: str,
        content_type: str,
        media_id: str,
        expires_in: int,
    ) -> tuple[str, dict[str, str]]: ...

    def create_download_url(self, object_key: str, expires_in: int) -> str: ...

    def get_metadata(self, object_key: str) -> StorageObjectMetadata: ...

    def download_bytes(self, object_key: str, generation: int | None) -> bytes: ...

    def replace_object(
        self,
        object_key: str,
        data: bytes,
        content_type: str,
        media_id: str,
        generation: int | None,
    ) -> StorageObjectMetadata: ...

    def put_derived_object(
        self,
        object_key: str,
        data: bytes,
        content_type: str,
        media_id: str,
        variant: str,
        checksum_sha256: str,
    ) -> StorageObjectMetadata: ...

    def delete_object(self, object_key: str, generation: int | None) -> None: ...


class DisabledStorageProvider:
    name = "gcs"
    enabled = False
    configured = False

    @staticmethod
    def _disabled():
        raise MediaStorageDisabled()

    def create_upload_url(
        self,
        object_key: str,
        content_type: str,
        media_id: str,
        expires_in: int,
    ) -> tuple[str, dict[str, str]]:
        return self._disabled()

    def create_download_url(self, object_key: str, expires_in: int) -> str:
        return self._disabled()

    def get_metadata(self, object_key: str) -> StorageObjectMetadata:
        return self._disabled()

    def download_bytes(self, object_key: str, generation: int | None) -> bytes:
        return self._disabled()

    def replace_object(
        self,
        object_key: str,
        data: bytes,
        content_type: str,
        media_id: str,
        generation: int | None,
    ) -> StorageObjectMetadata:
        return self._disabled()

    def put_derived_object(
        self,
        object_key: str,
        data: bytes,
        content_type: str,
        media_id: str,
        variant: str,
        checksum_sha256: str,
    ) -> StorageObjectMetadata:
        return self._disabled()

    def delete_object(self, object_key: str, generation: int | None) -> None:
        self._disabled()


class GoogleCloudStorageProvider:
    """Google Cloud Storage implementation with a private bucket and V4 URLs."""

    name = "gcs"
    enabled = True
    configured = True

    def __init__(self, settings: ServerSettings) -> None:
        if not settings.gcs_enabled or not settings.gcs_project_id or not settings.gcs_bucket_name:
            raise MediaStorageDisabled()
        try:
            if settings.gcs_credentials_file is not None:
                credentials = service_account.Credentials.from_service_account_file(
                    str(settings.gcs_credentials_file)
                )
            elif settings.gcs_credentials_json is not None:
                credentials = service_account.Credentials.from_service_account_info(
                    json.loads(settings.gcs_credentials_json.get_secret_value())
                )
            else:
                raise MediaStorageError("MEDIA_STORAGE_CONFIGURATION_INVALID")
            self.client = storage.Client(
                project=settings.gcs_project_id,
                credentials=credentials,
            )
        except MediaStorageError:
            raise
        except Exception:
            raise MediaStorageError("MEDIA_STORAGE_CONFIGURATION_INVALID") from None
        self.bucket_name = settings.gcs_bucket_name
        self.bucket = self.client.bucket(self.bucket_name)

    @staticmethod
    def _provider_failure(code: str, exc: Exception) -> MediaStorageError:
        if isinstance(exc, NotFound):
            return MediaObjectNotFound()
        if isinstance(exc, PreconditionFailed):
            return MediaObjectConflict()
        return MediaStorageError(code)

    def create_upload_url(
        self,
        object_key: str,
        content_type: str,
        media_id: str,
        expires_in: int,
    ) -> tuple[str, dict[str, str]]:
        headers = {
            "Content-Type": content_type,
            "x-goog-meta-media-id": media_id,
        }
        try:
            url = self.bucket.blob(object_key).generate_signed_url(
                version="v4",
                expiration=timedelta(seconds=expires_in),
                method="PUT",
                content_type=content_type,
                headers={"x-goog-meta-media-id": media_id},
                query_parameters={"ifGenerationMatch": "0"},
            )
            return url, headers
        except Exception as exc:
            raise self._provider_failure("MEDIA_UPLOAD_URL_FAILED", exc) from None

    def create_download_url(self, object_key: str, expires_in: int) -> str:
        try:
            return self.bucket.blob(object_key).generate_signed_url(
                version="v4",
                expiration=timedelta(seconds=expires_in),
                method="GET",
                response_disposition="inline",
            )
        except Exception as exc:
            raise self._provider_failure("MEDIA_DOWNLOAD_URL_FAILED", exc) from None

    def get_metadata(self, object_key: str) -> StorageObjectMetadata:
        blob = self.bucket.blob(object_key)
        try:
            blob.reload()
        except Exception as exc:
            raise self._provider_failure("MEDIA_METADATA_FAILED", exc) from None
        if blob.size is None:
            raise MediaStorageError("MEDIA_METADATA_INVALID")
        return StorageObjectMetadata(
            bucket_name=self.bucket_name,
            object_key=object_key,
            size_bytes=int(blob.size),
            content_type=blob.content_type,
            crc32c=blob.crc32c,
            generation=int(blob.generation) if blob.generation is not None else None,
            metadata={
                str(key): str(value)
                for key, value in (blob.metadata or {}).items()
            },
        )

    def download_bytes(self, object_key: str, generation: int | None) -> bytes:
        blob = self.bucket.blob(object_key, generation=generation)
        try:
            return blob.download_as_bytes(checksum="auto")
        except Exception as exc:
            raise self._provider_failure("MEDIA_DOWNLOAD_FAILED", exc) from None

    def replace_object(
        self,
        object_key: str,
        data: bytes,
        content_type: str,
        media_id: str,
        generation: int | None,
    ) -> StorageObjectMetadata:
        blob = self.bucket.blob(object_key)
        blob.metadata = {"media-id": media_id, "processed": "true"}
        try:
            blob.upload_from_string(
                data,
                content_type=content_type,
                checksum="auto",
                if_generation_match=generation,
            )
        except Exception as exc:
            raise self._provider_failure("MEDIA_PROCESSING_UPLOAD_FAILED", exc) from None
        return self.get_metadata(object_key)

    def put_derived_object(
        self,
        object_key: str,
        data: bytes,
        content_type: str,
        media_id: str,
        variant: str,
        checksum_sha256: str,
    ) -> StorageObjectMetadata:
        """Cria uma variante imutavel e aceita repeticao somente se for identica."""

        expected_metadata = {
            "media-id": media_id,
            "variant": variant,
            "checksum-sha256": checksum_sha256,
            "processed": "true",
        }
        blob = self.bucket.blob(object_key)
        blob.metadata = expected_metadata
        try:
            blob.upload_from_string(
                data,
                content_type=content_type,
                checksum="auto",
                if_generation_match=0,
            )
            return self.get_metadata(object_key)
        except PreconditionFailed:
            existing = self.get_metadata(object_key)
            if (
                existing.content_type == content_type
                and existing.size_bytes == len(data)
                and all(existing.metadata.get(key) == value for key, value in expected_metadata.items())
            ):
                return existing
            raise MediaObjectConflict() from None
        except Exception as exc:
            raise self._provider_failure("MEDIA_VARIANT_UPLOAD_FAILED", exc) from None

    def delete_object(self, object_key: str, generation: int | None) -> None:
        blob = self.bucket.blob(object_key, generation=generation)
        try:
            blob.delete(if_generation_match=generation)
        except NotFound:
            return
        except Exception as exc:
            raise self._provider_failure("MEDIA_DELETE_FAILED", exc) from None


def build_storage_provider(settings: ServerSettings) -> StorageProvider:
    if not settings.gcs_enabled:
        return DisabledStorageProvider()
    return GoogleCloudStorageProvider(settings)
