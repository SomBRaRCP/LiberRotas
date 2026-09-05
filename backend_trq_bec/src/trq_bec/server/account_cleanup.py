"""Limpeza administrativa dos documentos Firestore vinculados a uma conta."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from firebase_admin import firestore
from google.cloud.firestore_v1.base_query import FieldFilter


QUERY_BATCH_SIZE = 30
WRITE_BATCH_SIZE = 450


def _chunks(values: list[str], size: int) -> Iterable[list[str]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def delete_account_documents(uid: str) -> int:
    """Exclui dados sociais/pessoais e interações órfãs usando Firebase Admin.

    O backend usa credenciais administrativas porque algumas coleções não podem
    ser removidas pelo cliente e porque curtidas de terceiros podem apontar para
    conteúdo que deixou de existir.
    """

    database = firestore.client()
    references: dict[str, Any] = {}
    deleted_target_ids = {uid, f"profile:{uid}"}

    def remember(reference: Any) -> None:
        references[reference.path] = reference

    for collection_name in ("public_profiles", "private_profiles", "admin_users"):
        reference = database.collection(collection_name).document(uid)
        if reference.get().exists:
            remember(reference)

    owned_queries = (
        ("posts", "authorId"),
        ("network_interactions", "userId"),
        ("coupon_validations", "userId"),
        ("curated_places", "ownerId"),
        ("curated_places", "createdBy"),
        ("live_fairs", "ownerId"),
        ("live_fairs", "createdBy"),
    )
    for collection_name, field_name in owned_queries:
        query = database.collection(collection_name).where(
            filter=FieldFilter(field_name, "==", uid),
        )
        for snapshot in query.stream():
            remember(snapshot.reference)
            if collection_name == "posts":
                deleted_target_ids.add(snapshot.id)
                deleted_target_ids.add(f"post:{snapshot.id}")
            elif collection_name == "curated_places":
                deleted_target_ids.add(snapshot.id)
                deleted_target_ids.add(f"place:{snapshot.id}")
            elif collection_name == "live_fairs":
                deleted_target_ids.add(snapshot.id)
                deleted_target_ids.add(f"fair:{snapshot.id}")

    # Remove também curtidas/favoritos de terceiros que ficariam apontando para
    # perfil, publicação, ponto ou feira apagados.
    target_ids = sorted(deleted_target_ids)
    for target_chunk in _chunks(target_ids, QUERY_BATCH_SIZE):
        query = database.collection("network_interactions").where(
            filter=FieldFilter("targetId", "in", target_chunk),
        )
        for snapshot in query.stream():
            remember(snapshot.reference)

    ordered_references = list(references.values())
    for reference_chunk in _chunks(ordered_references, WRITE_BATCH_SIZE):
        batch = database.batch()
        for reference in reference_chunk:
            batch.delete(reference)
        batch.commit()

    return len(ordered_references)
