"""Collection is the M1 convergence layer for matching, mutation, and indexing.

Documents are kept in insertion order for deterministic teaching output.  The
separate ``IdIndex`` supplies uniqueness and direct identity lookup; M2 will
add secondary indexes and planning without changing this public CRUD surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

from minimongodb.bson import (
    CounterObjectIdGenerator,
    bson_equal,
    canonical_key,
    clone_document,
)
from minimongodb.errors import DuplicateKeyError, InvalidUpdateError
from minimongodb.index import IdIndex
from minimongodb.oplog.entry import Oplog, OplogEntry
from minimongodb.query import matches
from minimongodb.update import apply_operator_update, replacement_document


@dataclass(frozen=True, slots=True)
class InsertOneResult:
    inserted_id: Any


@dataclass(frozen=True, slots=True)
class InsertManyResult:
    inserted_ids: list[Any]


@dataclass(frozen=True, slots=True)
class UpdateResult:
    matched_count: int
    modified_count: int


@dataclass(frozen=True, slots=True)
class DeleteResult:
    deleted_count: int


class Collection:
    """A deterministic, single-writer collection with a unique ``_id`` index."""

    def __init__(
        self,
        name: str = "default",
        *,
        id_generator: Callable[[], Any] | None = None,
        oplog: Oplog | None = None,
    ) -> None:
        self.name = name
        self._id_generator = id_generator or CounterObjectIdGenerator()
        self._documents: list[dict[str, Any]] = []
        self._id_index = IdIndex()
        self.oplog = oplog if oplog is not None else Oplog()

    def insert_one(self, document: dict[str, Any]) -> InsertOneResult:
        return InsertOneResult(self.insert_many([document]).inserted_ids[0])

    def insert_many(self, documents: Iterable[dict[str, Any]]) -> InsertManyResult:
        candidates: list[dict[str, Any]] = []
        pending_ids: set[tuple[Any, ...]] = set()
        for source in documents:
            candidate = clone_document(source)
            if "_id" not in candidate:
                candidate["_id"] = self._id_generator()
            key = candidate["_id"]
            canonical = canonical_key(key)
            duplicate = self._id_index.contains(key) or canonical in pending_ids
            pending_ids.add(canonical)
            if duplicate:
                raise DuplicateKeyError(f"duplicate key for _id index: {key!r}")
            candidates.append(candidate)

        # Validate the whole batch, then durably publish one document at a time.
        for candidate in candidates:
            self.oplog.emit(
                self.name, "insert", candidate["_id"], clone_document(candidate)
            )
            self._documents.append(candidate)
            self._id_index.add(candidate)
        return InsertManyResult([candidate["_id"] for candidate in candidates])

    def find(self, query: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return [
            clone_document(document)
            for document in self._documents
            if matches(document, query)
        ]

    def find_one(self, query: dict[str, Any] | None = None) -> dict[str, Any] | None:
        for document in self._documents:
            if matches(document, query):
                return clone_document(document)
        return None

    def count_documents(self, query: dict[str, Any] | None = None) -> int:
        return sum(matches(document, query) for document in self._documents)

    def update_one(
        self, query: dict[str, Any], update: dict[str, Any]
    ) -> UpdateResult:
        return self._update(query, update, limit=1)

    def update_many(
        self, query: dict[str, Any], update: dict[str, Any]
    ) -> UpdateResult:
        return self._update(query, update, limit=None)

    def _update(
        self,
        query: dict[str, Any],
        update: dict[str, Any],
        *,
        limit: int | None,
    ) -> UpdateResult:
        if not isinstance(update, dict) or not update:
            raise InvalidUpdateError("update must be a non-empty document")
        has_operator = [key.startswith("$") for key in update]
        if not all(has_operator):
            if any(has_operator):
                raise InvalidUpdateError("cannot mix operator and replacement syntax")
            raise InvalidUpdateError("use replace_one for a replacement document")

        matched = modified = 0
        for position, original in enumerate(list(self._documents)):
            if not matches(original, query):
                continue
            matched += 1
            candidate = apply_operator_update(original, update)
            if not bson_equal(candidate, original):
                self.oplog.emit(
                    self.name,
                    "update",
                    original["_id"],
                    self._post_image_update(candidate, update),
                )
                self._replace_at(position, candidate)
                modified += 1
            if limit is not None and matched >= limit:
                break
        return UpdateResult(matched, modified)

    def replace_one(
        self, query: dict[str, Any], replacement: dict[str, Any]
    ) -> UpdateResult:
        if not isinstance(replacement, dict) or not replacement:
            raise InvalidUpdateError("replacement must be a non-empty document")
        if any(key.startswith("$") for key in replacement):
            raise InvalidUpdateError("replace_one requires a replacement document")
        for position, original in enumerate(self._documents):
            if matches(original, query):
                candidate = replacement_document(original, replacement)
                modified = not bson_equal(candidate, original)
                if modified:
                    self.oplog.emit(
                        self.name,
                        "replace",
                        original["_id"],
                        clone_document(candidate),
                    )
                    self._replace_at(position, candidate)
                return UpdateResult(1, int(modified))
        return UpdateResult(0, 0)

    def delete_one(self, query: dict[str, Any]) -> DeleteResult:
        return self._delete(query, limit=1)

    def delete_many(self, query: dict[str, Any]) -> DeleteResult:
        return self._delete(query, limit=None)

    def _delete(self, query: dict[str, Any], *, limit: int | None) -> DeleteResult:
        deleted = 0
        position = 0
        while position < len(self._documents):
            document = self._documents[position]
            if matches(document, query) and (limit is None or deleted < limit):
                self.oplog.emit(self.name, "delete", document["_id"])
                self._id_index.remove(document["_id"])
                self._documents.pop(position)
                deleted += 1
            else:
                position += 1
        return DeleteResult(deleted)

    def _replace_at(self, position: int, document: dict[str, Any]) -> None:
        key = self._documents[position]["_id"]
        self._documents[position] = document
        self._id_index.replace(key, document)

    @staticmethod
    def _post_image_update(
        candidate: dict[str, Any], requested_update: dict[str, Any]
    ) -> dict[str, Any]:
        """Rewrite action operators to idempotent final path assignments."""

        from minimongodb.bson import MISSING, get_path

        set_values: dict[str, Any] = {}
        unset_values: dict[str, str] = {}
        for operand in requested_update.values():
            for path in operand:
                value = get_path(candidate, path)
                if value is MISSING:
                    unset_values[path] = ""
                else:
                    set_values[path] = value
        payload: dict[str, Any] = {}
        if set_values:
            payload["$set"] = set_values
        if unset_values:
            payload["$unset"] = unset_values
        return payload

    def _apply_oplog_entry(self, entry: OplogEntry) -> None:
        """Recovery-only mutation path; deliberately emits no recursive log."""

        existing = self._id_index.get(entry.key)
        if entry.operation in {"insert", "replace"}:
            assert entry.payload is not None
            candidate = clone_document(entry.payload)
            if existing is None:
                self._documents.append(candidate)
                self._id_index.add(candidate)
            else:
                position = self._documents.index(existing)
                self._replace_at(position, candidate)
        elif entry.operation == "update":
            if existing is None:
                return
            assert entry.payload is not None
            position = self._documents.index(existing)
            candidate = apply_operator_update(existing, entry.payload)
            self._replace_at(position, candidate)
        elif entry.operation == "delete":
            if existing is not None:
                self._documents.remove(existing)
                self._id_index.remove(entry.key)
        else:
            raise ValueError(f"unknown oplog operation: {entry.operation}")
