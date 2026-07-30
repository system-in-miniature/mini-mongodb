"""Database wires collections to one durable oplog and startup recovery."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from minimongodb.bson import CounterObjectIdGenerator, ObjectId
from minimongodb.collection import Collection
from minimongodb.oplog import Oplog, OplogEntry, replay
from minimongodb.storage import Journal, load_recovery_state, write_checkpoint


def _object_id_values(value: Any):
    if isinstance(value, ObjectId):
        yield value.value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _object_id_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _object_id_values(child)


class Database:
    """Persistent single-writer database rooted at one explicit directory."""

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        recovery = load_recovery_state(self.directory)
        highest_sequence = max(
            [recovery.checkpoint_sequence]
            + [entry.sequence for entry in recovery.journal_entries]
        )
        id_values = [
            value
            for documents in recovery.collections.values()
            for document in documents
            for value in _object_id_values(document.get("_id"))
        ]
        id_values.extend(
            value
            for entry in recovery.journal_entries
            for value in _object_id_values(entry.key)
        )
        self._id_generator = CounterObjectIdGenerator(max(id_values, default=0) + 1)
        self._journal = Journal(self.directory / "journal.bin")
        self.oplog = Oplog(
            start_sequence=highest_sequence + 1,
            listener=self._journal.append,
        )
        names = set(recovery.collections)
        names.update(recovery.indexes)
        names.update(entry.collection for entry in recovery.journal_entries)
        self._collections = {
            name: Collection(
                name,
                id_generator=self._id_generator,
                oplog=self.oplog,
            )
            for name in sorted(names)
        }
        for name, documents in recovery.collections.items():
            collection = self._collections[name]
            for document in documents:
                collection._apply_oplog_entry(
                    OplogEntry(0, name, "insert", document["_id"], document)
                )
        for name, definitions in recovery.indexes.items():
            collection = self._collections[name]
            for definition in definitions:
                collection._restore_index(definition)
        replay(
            recovery.journal_entries,
            self._collections,
            after_sequence=recovery.checkpoint_sequence,
        )

    def get_collection(self, name: str) -> Collection:
        if name not in self._collections:
            self._collections[name] = Collection(
                name,
                id_generator=self._id_generator,
                oplog=self.oplog,
            )
        return self._collections[name]

    def __getitem__(self, name: str) -> Collection:
        return self.get_collection(name)

    def checkpoint(self) -> None:
        """Persist a snapshot tagged with the latest durable oplog sequence."""

        write_checkpoint(
            self.directory / "checkpoint.bin",
            {
                "sequence": self.oplog.last_sequence,
                "collections": {
                    name: collection.find()
                    for name, collection in sorted(self._collections.items())
                },
                "indexes": {
                    name: collection._index_definitions()
                    for name, collection in sorted(self._collections.items())
                },
            },
        )

    def inject_journal_tail_truncation(self, byte_count: int) -> int:
        """Teaching fault injector: remove bytes as if a frame write crashed."""

        if isinstance(byte_count, bool) or not isinstance(byte_count, int):
            raise TypeError("byte_count must be an integer")
        if byte_count <= 0:
            raise ValueError("byte_count must be positive")
        path = self.directory / "journal.bin"
        size = path.stat().st_size
        new_size = max(0, size - byte_count)
        with path.open("r+b") as stream:
            stream.truncate(new_size)
        return new_size
