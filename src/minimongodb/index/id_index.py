"""A direct map models MongoDB's automatically-created unique ``_id`` index."""

from __future__ import annotations

from typing import Any

from minimongodb.bson import canonical_key
from minimongodb.errors import DuplicateKeyError


class IdIndex:
    """Unique key-to-document map used for validation and direct lookup."""

    def __init__(self) -> None:
        self._documents: dict[tuple[Any, ...], dict[str, Any]] = {}

    def add(self, document: dict[str, Any]) -> None:
        value = document["_id"]
        key = canonical_key(value)
        if key in self._documents:
            raise DuplicateKeyError(f"duplicate key for _id index: {value!r}")
        self._documents[key] = document

    def remove(self, key: Any) -> None:
        self._documents.pop(canonical_key(key))

    def replace(self, key: Any, document: dict[str, Any]) -> None:
        self._documents[canonical_key(key)] = document

    def get(self, key: Any) -> dict[str, Any] | None:
        try:
            return self._documents.get(canonical_key(key))
        except TypeError:
            return None

    def contains(self, key: Any) -> bool:
        try:
            return canonical_key(key) in self._documents
        except TypeError:
            return False
