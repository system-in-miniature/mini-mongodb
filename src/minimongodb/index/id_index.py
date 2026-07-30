"""A direct map models MongoDB's automatically-created unique ``_id`` index."""

from __future__ import annotations

from typing import Any

from minimongodb.errors import DuplicateKeyError


class IdIndex:
    """Unique key-to-document map used for validation and direct lookup."""

    def __init__(self) -> None:
        self._documents: dict[Any, dict[str, Any]] = {}

    def add(self, document: dict[str, Any]) -> None:
        key = document["_id"]
        try:
            if key in self._documents:
                raise DuplicateKeyError(f"duplicate key for _id index: {key!r}")
            self._documents[key] = document
        except TypeError as error:
            raise TypeError("_id must be hashable in MiniMongoDB") from error

    def remove(self, key: Any) -> None:
        self._documents.pop(key)

    def replace(self, key: Any, document: dict[str, Any]) -> None:
        self._documents[key] = document

    def get(self, key: Any) -> dict[str, Any] | None:
        try:
            return self._documents.get(key)
        except TypeError:
            return None

    def contains(self, key: Any) -> bool:
        try:
            return key in self._documents
        except TypeError:
            return False
