from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from trq_bec.server.community import (
    CommunityDocumentConflict,
    CommunityDocumentForbidden,
    FirebaseCommunityPublisher,
)
from trq_bec.server.models import (
    CommunityPostCreateRequest,
    CommunityPostUpdateRequest,
    CuratedPlaceCreateRequest,
    PublicProfileRecord,
)


class FakeSnapshot:
    def __init__(self, data: dict[str, object] | None) -> None:
        self._data = data

    def to_dict(self) -> dict[str, object] | None:
        return self._data

    @property
    def exists(self) -> bool:
        return self._data is not None


class FakeReference:
    def __init__(self, database: "FakeFirestore", collection_name: str, document_id: str) -> None:
        self.database = database
        self.collection_name = collection_name
        self.id = document_id

    def get(self, *, timeout: int | None = None, transaction=None) -> FakeSnapshot:
        if timeout is not None:
            assert timeout == 10
        if self.collection_name == "public_profiles":
            return FakeSnapshot(self.database.profiles.get(self.id))
        return FakeSnapshot(self.database.writes.get((self.collection_name, self.id)))

    def set(self, data: dict[str, object]) -> None:
        self.database.writes[(self.collection_name, self.id)] = data

    def update(self, data: dict[str, object]) -> None:
        self.database.writes[(self.collection_name, self.id)].update(data)

    def delete(self) -> None:
        self.database.writes.pop((self.collection_name, self.id), None)


class FakeCollection:
    def __init__(self, database: "FakeFirestore", name: str) -> None:
        self.database = database
        self.name = name

    def document(self, document_id: str | None = None) -> FakeReference:
        return FakeReference(self.database, self.name, document_id or "generated-post-id")

    def where(self, *, filter) -> "FakeQuery":
        return FakeQuery(
            self.database,
            self.name,
            [(filter.field_path, filter.value)],
        )


class FakeQuery:
    def __init__(
        self,
        database: "FakeFirestore",
        collection_name: str,
        filters: list[tuple[str, object]],
    ) -> None:
        self.database = database
        self.collection_name = collection_name
        self.filters = filters
        self.maximum = 100

    def limit(self, maximum: int) -> "FakeQuery":
        self.maximum = maximum
        return self

    def stream(self):
        matches = []
        for (collection_name, _document_id), data in self.database.writes.items():
            if collection_name != self.collection_name:
                continue
            if all(data.get(field_name) == expected for field_name, expected in self.filters):
                matches.append(FakeSnapshot(data))
        return iter(matches[: self.maximum])


class FakeTransaction:
    def set(self, reference: FakeReference, data: dict[str, object]) -> None:
        reference.set(data)

    def delete(self, reference: FakeReference) -> None:
        reference.delete()


class FakeFirestore:
    def __init__(self) -> None:
        self.profiles = {
            "verified-uid": {
                "displayName": "  Perfil Verificado  ",
                "role": "admin",
                "city": " Pinhais ",
                "category": " Artesanato ",
                "avatarUri": "https://cdn.example.test/avatar.jpg",
            }
        }
        self.writes: dict[tuple[str, str], dict[str, object]] = {}

    def collection(self, name: str) -> FakeCollection:
        return FakeCollection(self, name)

    def transaction(self) -> FakeTransaction:
        return FakeTransaction()


def test_firebase_post_publisher_uses_verified_identity_and_public_profile() -> None:
    database = FakeFirestore()
    media_id = "123e4567-e89b-42d3-a456-426614174000"
    request = CommunityPostCreateRequest.model_validate(
        {
            "text": "Conteudo confiavel",
            "media": {"type": "image", "media_id": media_id},
        }
    )

    with patch("trq_bec.server.community.firestore.client", return_value=database):
        document_id = FirebaseCommunityPublisher().create_post(
            "verified-uid",
            "verified@example.test",
            "visitor",
            request,
            1_783_900_000_000,
            "post-authoritative-id",
        )

    assert document_id == "post-authoritative-id"
    saved = database.writes[("posts", document_id)]
    assert saved["id"] == document_id
    assert saved["authorId"] == "verified-uid"
    assert saved["author"] == "Perfil Verificado"
    assert saved["authorRole"] == "visitor"
    assert saved["authorCity"] == "Pinhais"
    assert saved["authorCategory"] == "Artesanato"
    assert saved["authorAvatarUri"] == "https://cdn.example.test/avatar.jpg"
    assert saved["text"] == "Conteudo confiavel"
    assert saved["media"] == {
        "type": "image",
        "mediaId": media_id,
    }
    assert "email" not in saved
    assert saved["createdAt"] == "2026-07-12T23:46:40Z"


def test_firebase_post_publisher_generates_document_id_when_optional_id_is_omitted() -> None:
    database = FakeFirestore()
    request = CommunityPostCreateRequest.model_validate({"text": "Somente texto"})

    with patch("trq_bec.server.community.firestore.client", return_value=database):
        document_id = FirebaseCommunityPublisher().create_post(
            "verified-uid",
            "verified@example.test",
            "visitor",
            request,
            1_783_900_000_000,
        )

    assert document_id == "generated-post-id"
    assert database.writes[("posts", document_id)]["media"] is None


def test_firebase_post_publisher_edits_and_deletes_only_owned_post() -> None:
    database = FakeFirestore()
    publisher = FirebaseCommunityPublisher()
    request = CommunityPostCreateRequest.model_validate({"text": "Texto inicial"})

    with patch("trq_bec.server.community.firestore.client", return_value=database):
        document_id = publisher.create_post(
            "verified-uid",
            "verified@example.test",
            "visitor",
            request,
            1_783_900_000_000,
            "post-owned-id",
        )
        publisher.update_post(
            "verified-uid",
            document_id,
            CommunityPostUpdateRequest.model_validate({"text": "Texto corrigido"}),
            1_783_900_001_000,
        )
        saved = database.writes[("posts", document_id)]
        assert saved["text"] == "Texto corrigido"
        assert saved["updatedAtMs"] == 1_783_900_001_000
        publisher.delete_post("verified-uid", document_id)

    assert ("posts", document_id) not in database.writes


def test_firebase_public_profile_sync_contains_only_public_fields() -> None:
    database = FakeFirestore()
    created_at = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
    profile = PublicProfileRecord(
        firebase_uid="verified-uid",
        display_name="Perfil Verificado",
        normalized_name="perfil verificado",
        role="visitor",
        city="Pinhais",
        address="Rua das Flores, 100",
        category="Turismo",
        interests=("Feiras", "Parques"),
        avatar_uri="https://cdn.example.test/avatar.jpg",
        created_at=created_at,
        updated_at=created_at,
    )

    with patch("trq_bec.server.community.firestore.client", return_value=database):
        FirebaseCommunityPublisher().upsert_public_profile(profile)

    saved = database.writes[("public_profiles", "verified-uid")]
    assert saved["userId"] == "verified-uid"
    assert saved["displayName"] == "Perfil Verificado"
    assert saved["role"] == "visitor"
    assert saved["interests"] == ["Feiras", "Parques"]
    assert saved["createdAtMs"] == 1_784_116_800_000
    assert "email" not in saved
    assert "normalizedName" not in saved
    assert "pixKey" not in saved


def test_firebase_place_publisher_limits_owner_to_one_place_and_allows_owned_delete() -> None:
    database = FakeFirestore()
    publisher = FirebaseCommunityPublisher()
    request = CuratedPlaceCreateRequest.model_validate(
        {
            "name": "Ateliê Local",
            "address": "Rua das Flores, 100",
            "category": "artesanato",
            "latitude": -25.44,
            "longitude": -49.19,
        }
    )

    with (
        patch("trq_bec.server.community.firestore.client", return_value=database),
        patch(
            "trq_bec.server.community.firestore.transactional",
            side_effect=lambda function: function,
        ),
    ):
        document_id = publisher.create_place(
            "verified-uid",
            "verified@example.test",
            request,
            1_783_900_000_000,
        )
        assert document_id == "verified-uid"
        with pytest.raises(CommunityDocumentConflict):
            publisher.create_place(
                "verified-uid",
                "verified@example.test",
                request,
                1_783_900_001_000,
            )
        with pytest.raises(CommunityDocumentForbidden):
            publisher.delete_place("other-uid", document_id)
        publisher.delete_place("verified-uid", document_id)

    assert ("curated_places", document_id) not in database.writes
