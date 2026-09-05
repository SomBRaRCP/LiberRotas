"""Publicação autoritativa de pontos e feiras no Firestore via Firebase Admin."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

from firebase_admin import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from .models import (
    CommunityPostCreateRequest,
    CommunityPostUpdateRequest,
    CuratedPlaceCreateRequest,
    LiveFairCreateRequest,
    PublicProfileRecord,
)


class CommunityPublishError(RuntimeError):
    """Falha de infraestrutura sem expor detalhes do Firebase ao cliente."""


class CommunityDocumentNotFound(CommunityPublishError):
    pass


class CommunityDocumentForbidden(CommunityPublishError):
    pass


class CommunityDocumentConflict(CommunityPublishError):
    pass


class CommunityPublisher(Protocol):
    def upsert_public_profile(self, profile: PublicProfileRecord) -> None: ...

    def create_post(
        self,
        uid: str,
        email: str | None,
        role: str,
        request: CommunityPostCreateRequest,
        created_at_ms: int,
        document_id: str | None = None,
    ) -> str: ...

    def update_post(
        self,
        uid: str,
        post_id: str,
        request: CommunityPostUpdateRequest,
        updated_at_ms: int,
    ) -> None: ...

    def delete_post(self, uid: str, post_id: str) -> None: ...

    def create_place(
        self,
        uid: str,
        email: str | None,
        request: CuratedPlaceCreateRequest,
        created_at_ms: int,
    ) -> str: ...

    def delete_place(self, uid: str, place_id: str) -> None: ...

    def create_live_fair(
        self,
        uid: str,
        email: str | None,
        request: LiveFairCreateRequest,
        created_at_ms: int,
        status: str,
    ) -> str: ...

    def end_live_fair(self, uid: str, fair_id: str, ended_at_ms: int) -> None: ...

    def delete_live_fair(self, uid: str, fair_id: str) -> None: ...

    def owns_live_fair(self, uid: str, fair_id: str) -> bool: ...


class FirebaseCommunityPublisher:
    """Escreve com credencial administrativa; clientes não recebem esse acesso."""

    def upsert_public_profile(self, profile: PublicProfileRecord) -> None:
        try:
            created_at_ms = int(profile.created_at.timestamp() * 1000)
            updated_at_ms = int(profile.updated_at.timestamp() * 1000)
            firestore.client().collection("public_profiles").document(
                profile.firebase_uid
            ).set(
                {
                    "userId": profile.firebase_uid,
                    "displayName": profile.display_name,
                    "role": profile.role,
                    "city": profile.city,
                    "address": profile.address,
                    "category": profile.category,
                    "interests": list(profile.interests),
                    "avatarUri": profile.avatar_uri,
                    "createdAtMs": created_at_ms,
                    "updatedAtMs": updated_at_ms,
                    "privacy": {
                        "lgpdNoticeVersion": "2026-06-23",
                        "syncedAtMs": updated_at_ms,
                        "minimizedFields": [
                            "userId",
                            "displayName",
                            "role",
                            "city",
                            "address",
                            "category",
                            "interests",
                            "avatarUri",
                            "createdAtMs",
                        ],
                    },
                }
            )
        except Exception as exc:
            raise CommunityPublishError("COMMUNITY_FIRESTORE_WRITE_FAILED") from exc

    @staticmethod
    def _owner_name(database, uid: str, email: str | None) -> str:
        snapshot = database.collection("public_profiles").document(uid).get(timeout=10)
        data = snapshot.to_dict() or {}
        display_name = data.get("displayName")
        if isinstance(display_name, str) and 2 <= len(display_name.strip()) <= 100:
            return display_name.strip()
        email_name = (email or "").split("@", 1)[0].strip()
        return email_name[:100] if len(email_name) >= 2 else "Empreendedor LiberRotas"

    @staticmethod
    def _public_author(
        database,
        uid: str,
        email: str | None,
        role: str,
    ) -> dict[str, Any]:
        snapshot = database.collection("public_profiles").document(uid).get(timeout=10)
        profile = snapshot.to_dict() or {}

        def optional_text(field: str, max_length: int) -> str | None:
            value = profile.get(field)
            if not isinstance(value, str):
                return None
            normalized = value.strip()
            return normalized[:max_length] if normalized else None

        display_name = optional_text("displayName", 100)
        if display_name is None:
            email_name = (email or "").split("@", 1)[0].strip()
            display_name = email_name[:100] if len(email_name) >= 2 else "Pessoa LiberRotas"

        avatar_uri = optional_text("avatarUri", 4096)
        if avatar_uri is not None and not avatar_uri.startswith(("http://", "https://")):
            avatar_uri = None

        return {
            "authorId": uid,
            "author": display_name,
            "authorRole": role,
            "authorCity": optional_text("city", 120),
            "authorCategory": optional_text("category", 160),
            "authorAvatarUri": avatar_uri,
        }

    def create_post(
        self,
        uid: str,
        email: str | None,
        role: str,
        request: CommunityPostCreateRequest,
        created_at_ms: int,
        document_id: str | None = None,
    ) -> str:
        try:
            database = firestore.client()
            reference = database.collection("posts").document(document_id)
            created_at = datetime.fromtimestamp(
                created_at_ms / 1000,
                tz=timezone.utc,
            ).isoformat().replace("+00:00", "Z")
            media = (
                {
                    "type": "image",
                    "mediaId": request.media.media_id,
                }
                if request.media is not None
                else None
            )
            reference.set(
                {
                    "id": reference.id,
                    **self._public_author(database, uid, email, role),
                    "text": request.text,
                    "createdAt": created_at,
                    "createdAtMs": created_at_ms,
                    # Firestore recebe apenas o identificador opaco. A URL
                    # temporaria e resolvida pelo backend, nunca persistida no feed.
                    "media": media,
                    "privacy": {
                        "lgpdNoticeVersion": "2026-06-23",
                        "syncedAtMs": created_at_ms,
                        "minimizedFields": [
                            "authorId",
                            "author",
                            "authorRole",
                            "authorCity",
                            "authorCategory",
                            "text",
                            "createdAt",
                        ],
                    },
                }
            )
            return reference.id
        except CommunityPublishError:
            raise
        except Exception as exc:
            raise CommunityPublishError("COMMUNITY_FIRESTORE_WRITE_FAILED") from exc

    @staticmethod
    def _owned_post_reference(uid: str, post_id: str):
        database = firestore.client()
        reference = database.collection("posts").document(post_id)
        snapshot = reference.get(timeout=10)
        if not snapshot.exists:
            raise CommunityDocumentNotFound("COMMUNITY_POST_NOT_FOUND")
        data = snapshot.to_dict() or {}
        if data.get("authorId") != uid:
            raise CommunityDocumentForbidden("COMMUNITY_POST_FORBIDDEN")
        return reference

    def update_post(
        self,
        uid: str,
        post_id: str,
        request: CommunityPostUpdateRequest,
        updated_at_ms: int,
    ) -> None:
        try:
            reference = self._owned_post_reference(uid, post_id)
            updated_at = datetime.fromtimestamp(
                updated_at_ms / 1000,
                tz=timezone.utc,
            ).isoformat().replace("+00:00", "Z")
            reference.update(
                {
                    "text": request.text,
                    "updatedAt": updated_at,
                    "updatedAtMs": updated_at_ms,
                    "privacy.syncedAtMs": updated_at_ms,
                }
            )
        except (CommunityDocumentNotFound, CommunityDocumentForbidden):
            raise
        except Exception as exc:
            raise CommunityPublishError("COMMUNITY_FIRESTORE_WRITE_FAILED") from exc

    def delete_post(self, uid: str, post_id: str) -> None:
        try:
            reference = self._owned_post_reference(uid, post_id)
            reference.delete()
        except (CommunityDocumentNotFound, CommunityDocumentForbidden):
            raise
        except Exception as exc:
            raise CommunityPublishError("COMMUNITY_FIRESTORE_WRITE_FAILED") from exc

    def create_place(
        self,
        uid: str,
        email: str | None,
        request: CuratedPlaceCreateRequest,
        created_at_ms: int,
    ) -> str:
        try:
            database = firestore.client()
            collection = database.collection("curated_places")
            existing_query = collection.where(
                filter=FieldFilter("ownerId", "==", uid)
            ).limit(10)
            existing_place = next(
                (
                    snapshot
                    for snapshot in existing_query.stream()
                    if (snapshot.to_dict() or {}).get("status") == "approved"
                ),
                None,
            )
            if existing_place is not None:
                raise CommunityDocumentConflict("CURATED_PLACE_ALREADY_EXISTS")

            reference = collection.document(uid)
            transaction = database.transaction()
            data = {
                "ownerId": uid,
                "createdBy": uid,
                "ownerName": self._owner_name(database, uid, email),
                "name": request.name,
                "address": request.address,
                "category": request.category,
                "latitude": request.latitude,
                "longitude": request.longitude,
                "createdAtMs": created_at_ms,
                "status": "approved",
            }

            @firestore.transactional
            def create(transaction_value) -> None:
                snapshot = reference.get(transaction=transaction_value)
                if snapshot.exists and (snapshot.to_dict() or {}).get("status") == "approved":
                    raise CommunityDocumentConflict("CURATED_PLACE_ALREADY_EXISTS")
                transaction_value.set(reference, data)

            create(transaction)
            return reference.id
        except CommunityPublishError:
            raise
        except Exception as exc:
            raise CommunityPublishError("COMMUNITY_FIRESTORE_WRITE_FAILED") from exc

    def delete_place(self, uid: str, place_id: str) -> None:
        try:
            database = firestore.client()
            reference = database.collection("curated_places").document(place_id)
            transaction = database.transaction()

            @firestore.transactional
            def remove(transaction_value) -> None:
                snapshot = reference.get(transaction=transaction_value)
                if not snapshot.exists:
                    raise CommunityDocumentNotFound("CURATED_PLACE_NOT_FOUND")
                data = snapshot.to_dict() or {}
                if (data.get("ownerId") or data.get("createdBy")) != uid:
                    raise CommunityDocumentForbidden("CURATED_PLACE_NOT_OWNED")
                transaction_value.delete(reference)

            remove(transaction)
        except CommunityPublishError:
            raise
        except Exception as exc:
            raise CommunityPublishError("COMMUNITY_FIRESTORE_WRITE_FAILED") from exc

    def create_live_fair(
        self,
        uid: str,
        email: str | None,
        request: LiveFairCreateRequest,
        created_at_ms: int,
        status: str,
    ) -> str:
        try:
            database = firestore.client()
            reference = database.collection("live_fairs").document()
            reference.set(
                {
                    "ownerId": uid,
                    "createdBy": uid,
                    "ownerName": self._owner_name(database, uid, email),
                    "name": request.name,
                    "address": request.address,
                    "latitude": request.latitude,
                    "longitude": request.longitude,
                    "startsAtMs": request.starts_at_ms,
                    "endsAtMs": request.ends_at_ms,
                    "createdAtMs": created_at_ms,
                    "updatedAtMs": created_at_ms,
                    "status": status,
                }
            )
            return reference.id
        except CommunityPublishError:
            raise
        except Exception as exc:
            raise CommunityPublishError("COMMUNITY_FIRESTORE_WRITE_FAILED") from exc

    def owns_live_fair(self, uid: str, fair_id: str) -> bool:
        try:
            snapshot = (
                firestore.client()
                .collection("live_fairs")
                .document(fair_id)
                .get(timeout=10)
            )
            data = snapshot.to_dict() or {}
            owner_uid = data.get("ownerId") or data.get("createdBy")
            return owner_uid == uid and data.get("status") not in {
                "ended",
                "deleted",
            }
        except Exception as exc:
            raise CommunityPublishError("COMMUNITY_FIRESTORE_READ_FAILED") from exc

    def end_live_fair(self, uid: str, fair_id: str, ended_at_ms: int) -> None:
        try:
            database = firestore.client()
            reference = database.collection("live_fairs").document(fair_id)
            transaction = database.transaction()

            @firestore.transactional
            def finish(transaction_value) -> None:
                snapshot = reference.get(transaction=transaction_value)
                if not snapshot.exists:
                    raise CommunityDocumentNotFound("LIVE_FAIR_NOT_FOUND")
                data = snapshot.to_dict() or {}
                if (data.get("ownerId") or data.get("createdBy")) != uid:
                    raise CommunityDocumentForbidden("LIVE_FAIR_NOT_OWNED")
                if data.get("status") == "ended":
                    return
                if data.get("status") not in {"scheduled", "live"}:
                    raise CommunityDocumentConflict("LIVE_FAIR_NOT_ACTIVE")
                transaction_value.update(
                    reference,
                    {
                        "status": "ended",
                        "endedAtMs": ended_at_ms,
                        "endReason": "manual",
                        "updatedAtMs": ended_at_ms,
                    },
                )

            finish(transaction)
        except CommunityPublishError:
            raise
        except Exception as exc:
            raise CommunityPublishError("COMMUNITY_FIRESTORE_WRITE_FAILED") from exc

    def delete_live_fair(self, uid: str, fair_id: str) -> None:
        try:
            database = firestore.client()
            reference = database.collection("live_fairs").document(fair_id)
            transaction = database.transaction()

            @firestore.transactional
            def remove(transaction_value) -> None:
                snapshot = reference.get(transaction=transaction_value)
                if not snapshot.exists:
                    raise CommunityDocumentNotFound("LIVE_FAIR_NOT_FOUND")
                data = snapshot.to_dict() or {}
                if (data.get("ownerId") or data.get("createdBy")) != uid:
                    raise CommunityDocumentForbidden("LIVE_FAIR_NOT_OWNED")
                transaction_value.delete(reference)

            remove(transaction)
        except CommunityPublishError:
            raise
        except Exception as exc:
            raise CommunityPublishError("COMMUNITY_FIRESTORE_WRITE_FAILED") from exc
