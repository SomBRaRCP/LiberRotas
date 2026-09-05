from __future__ import annotations

import unittest
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

from trq_bec.server.account_cleanup import delete_account_documents


@dataclass
class FakeSnapshot:
    reference: "FakeReference"
    exists: bool = True

    @property
    def id(self) -> str:
        return self.reference.path.rsplit("/", 1)[-1]


class FakeReference:
    def __init__(self, database: "FakeFirestore", path: str) -> None:
        self.database = database
        self.path = path

    def get(self) -> FakeSnapshot:
        return FakeSnapshot(self, self.path in self.database.documents)


class FakeQuery:
    def __init__(self, database: "FakeFirestore", collection_name: str, field_filter: Any) -> None:
        self.database = database
        self.collection_name = collection_name
        self.field_filter = field_filter

    def stream(self):
        prefix = f"{self.collection_name}/"
        for path, data in list(self.database.documents.items()):
            if not path.startswith(prefix):
                continue
            value = data.get(self.field_filter.field_path)
            expected = self.field_filter.value
            matches = value == expected if self.field_filter.op_string == "==" else value in expected
            if matches:
                yield FakeSnapshot(FakeReference(self.database, path))


class FakeCollection:
    def __init__(self, database: "FakeFirestore", name: str) -> None:
        self.database = database
        self.name = name

    def document(self, document_id: str) -> FakeReference:
        return FakeReference(self.database, f"{self.name}/{document_id}")

    def where(self, *, filter: Any) -> FakeQuery:
        return FakeQuery(self.database, self.name, filter)


class FakeBatch:
    def __init__(self, database: "FakeFirestore") -> None:
        self.database = database
        self.pending: list[str] = []

    def delete(self, reference: FakeReference) -> None:
        self.pending.append(reference.path)

    def commit(self) -> None:
        self.database.commits.append(list(self.pending))
        for path in self.pending:
            self.database.documents.pop(path, None)


class FakeFirestore:
    def __init__(self, documents: dict[str, dict[str, Any]]) -> None:
        self.documents = dict(documents)
        self.commits: list[list[str]] = []

    def collection(self, name: str) -> FakeCollection:
        return FakeCollection(self, name)

    def batch(self) -> FakeBatch:
        return FakeBatch(self)


class AccountCleanupTests(unittest.TestCase):
    def test_deletes_owned_documents_and_orphan_interactions(self) -> None:
        uid = "owner-uid"
        unrelated_path = "posts/post-unrelated"
        database = FakeFirestore(
            {
                f"public_profiles/{uid}": {"userId": uid},
                f"private_profiles/{uid}": {"userId": uid},
                "posts/post-owned": {"authorId": uid},
                "network_interactions/own-like": {"userId": uid, "targetId": "post-other"},
                "network_interactions/profile-like": {"userId": "visitor-1", "targetId": f"profile:{uid}"},
                "network_interactions/fair-like": {"userId": "visitor-2", "targetId": "fair:fair-owned"},
                "coupon_validations/validation-owned": {"userId": uid},
                "curated_places/place-owned": {"ownerId": uid, "createdBy": uid},
                "live_fairs/fair-owned": {"ownerId": uid, "createdBy": uid},
                unrelated_path: {"authorId": "someone-else"},
            }
        )

        with patch("trq_bec.server.account_cleanup.firestore.client", return_value=database):
            deleted = delete_account_documents(uid)

        self.assertEqual(deleted, 9)
        self.assertEqual(set(database.documents), {unrelated_path})
        self.assertEqual(len(database.commits), 1)
        self.assertEqual(len(database.commits[0]), 9)


if __name__ == "__main__":
    unittest.main()
