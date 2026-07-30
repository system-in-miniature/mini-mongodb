"""Idempotent application of oplog post-images to collections."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from minimongodb.collection import Collection
from minimongodb.oplog.entry import OplogEntry


def replay(
    entries: Iterable[OplogEntry],
    target: Collection | Mapping[str, Collection],
    *,
    after_sequence: int = 0,
) -> int:
    """Apply entries after a checkpoint sequence and return the last seen one."""

    last_sequence = after_sequence
    for entry in entries:
        if entry.sequence <= after_sequence:
            continue
        collection = (
            target
            if isinstance(target, Collection)
            else target[entry.collection]
        )
        collection._apply_oplog_entry(entry)
        last_sequence = max(last_sequence, entry.sequence)
    return last_sequence
