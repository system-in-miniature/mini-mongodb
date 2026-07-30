"""Deterministic oplog entry model.

User updates describe an action (for example, "increment by three").  Oplog
updates instead describe the resulting assignment ("set count to five").
Repeating an action changes state twice; repeating an assignment converges on
the same state.  That is why collection integration rewrites every modified
path to its post-image.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from minimongodb.bson import clone_document


@dataclass(frozen=True, slots=True)
class OplogEntry:
    """One post-image-oriented mutation in a named collection."""

    sequence: int
    collection: str
    operation: str
    key: Any
    payload: dict[str, Any] | None = None


class Oplog:
    """Append-only v1 log; bounded/capped retention is deliberately M3."""

    def __init__(
        self,
        *,
        start_sequence: int = 1,
        listener: Callable[[OplogEntry], None] | None = None,
    ) -> None:
        self._entries: list[OplogEntry] = []
        self._next_sequence = start_sequence
        self._listener = listener

    def __iter__(self) -> Iterator[OplogEntry]:
        return iter(self._entries)

    @property
    def last_sequence(self) -> int:
        return self._next_sequence - 1

    def emit(
        self,
        collection: str,
        operation: str,
        key: Any,
        payload: dict[str, Any] | None = None,
    ) -> OplogEntry:
        entry = OplogEntry(
            sequence=self._next_sequence,
            collection=collection,
            operation=operation,
            key=key,
            payload=clone_document(payload) if payload is not None else None,
        )
        self._next_sequence += 1
        self._entries.append(entry)
        if self._listener is not None:
            # Persistence observes only complete in-memory mutations.
            self._listener(entry)
        return entry
