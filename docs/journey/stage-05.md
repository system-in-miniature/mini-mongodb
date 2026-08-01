# Stage 05 · Journal-first identity boundary

### Goal

Build journal-first identity boundary and explain its boundary from an executable counterexample, runtime state, and the critical statement.

??? note "Deliverable files"
    - `src/minimongodb/bson/__init__.py`
    - `src/minimongodb/bson/types.py`
    - `src/minimongodb/collection.py`
    - `src/minimongodb/index/id_index.py`
    - `src/minimongodb/oplog/entry.py`
    - `src/minimongodb/storage/checkpoint.py`
    - `src/minimongodb/storage/journal.py`
    - `tests/test_crud.py`
    - `tests/test_oplog.py`
    - `tests/test_recovery.py`
    - `tests/test_storage.py`

### The problem at this point

The first implementation exposed three crash edges: publishing before journal success, using non-canonical `_id` keys, and renaming a checkpoint without syncing its directory.

### Test contract

#### See the failure first

Failure injection interrupts open, write, and fsync for insert, update, and delete; identity cases compare bool, numbers, NaN, and nested BSON; filesystem spies require directory fsync.

??? note "File diff: tests/test_crud.py"
    ```diff
    diff --git a/tests/test_crud.py b/tests/test_crud.py
    index 6c30385f4990cdd155e445a456cfe1044589f75f..99e255fffbacf06eb770ed980798d1c204de3633 100644
    --- a/tests/test_crud.py
    +++ b/tests/test_crud.py
    @@ -1,5 +1,7 @@
     """Public CRUD contract and automatic unique ``_id`` index."""

    +from math import nan
    +
     import pytest

     from minimongodb import Collection, CounterObjectIdGenerator, ObjectId
    @@ -35,6 +37,37 @@ def test_id_index_rejects_duplicate_key_without_partial_insert_many() -> None:
         assert collection.find({}) == [{"_id": "same", "n": 1}]


    +def test_id_index_keeps_bool_distinct_from_numeric_ids() -> None:
    +    collection = Collection()
    +    collection.insert_many([{"_id": True}, {"_id": 1}])
    +    assert collection.find() == [{"_id": True}, {"_id": 1}]
    +
    +
    +def test_id_index_uses_bson_numeric_equality_across_int_and_float() -> None:
    +    collection = Collection()
    +    collection.insert_one({"_id": 1})
    +    with pytest.raises(DuplicateKeyError):
    +        collection.insert_one({"_id": 1.0})
    +
    +    boundary = Collection()
    +    boundary.insert_many([{"_id": 2**53 + 1}, {"_id": float(2**53 + 1)}])
    +    assert len(boundary.find()) == 2
    +
    +
    +def test_id_index_canonicalizes_nan_and_nested_bson_values() -> None:
    +    nan_ids = Collection()
    +    nan_ids.insert_one({"_id": nan})
    +    with pytest.raises(DuplicateKeyError):
    +        nan_ids.insert_one({"_id": nan})
    +
    +    nested_ids = Collection()
    +    nested_ids.insert_one({"_id": {"a": [True, 1], "b": 2}})
    +    with pytest.raises(DuplicateKeyError):
    +        nested_ids.insert_one({"_id": {"a": [True, 1], "b": 2.0}})
    +    nested_ids.insert_one({"_id": {"b": 2, "a": [True, 1]}})
    +    assert len(nested_ids.find()) == 2
    +
    +
     def test_delete_one_and_many_report_deleted_counts() -> None:
         collection = Collection()
         collection.insert_many(
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

Failure injection interrupts open, write, and fsync for insert, update, and delete; identity cases compare bool, numbers, NaN, and nested BSON; filesystem spies require directory fsync.

**Key test statement**

```python
assert collection.find() == [{"_id": True}, {"_id": 1}]
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/test_oplog.py"
    ```diff
    diff --git a/tests/test_oplog.py b/tests/test_oplog.py
    index d19f44214c005f792ae2ebc7c21fb28b69b37a51..1d7423280671e0d361f60869756752bc1713dd41 100644
    --- a/tests/test_oplog.py
    +++ b/tests/test_oplog.py
    @@ -1,5 +1,7 @@
     """Oplog entries are deterministic state assignments, not user commands."""

    +import pytest
    +
     from minimongodb import Collection
     from minimongodb.oplog import Oplog, replay

    @@ -62,3 +64,59 @@ def test_post_image_keeps_only_the_final_state_for_a_repeated_path() -> None:
         replay(source.oplog, target)
         replay(source.oplog, target)
         assert target.find_one({"_id": 1})["value"] == "final"
    +
    +
    +def test_batch_stops_at_first_durability_failure_and_keeps_committed_prefix() -> None:
    +    def durable_append(entry) -> None:
    +        if entry.sequence == 2:
    +            raise OSError("injected journal failure")
    +
    +    oplog = Oplog(listener=durable_append)
    +    collection = Collection("items", oplog=oplog)
    +
    +    with pytest.raises(OSError, match="injected journal failure"):
    +        collection.insert_many([{"_id": 1}, {"_id": 2}, {"_id": 3}])
    +
    +    assert collection.find() == [{"_id": 1}]
    +    assert [entry.sequence for entry in oplog] == [1]
    +    assert oplog.last_sequence == 1
    +
    +
    +@pytest.mark.parametrize("operation", ["update", "delete"])
    +def test_multi_document_mutation_keeps_only_durable_prefix(operation: str) -> None:
    +    fail_at: int | None = None
    +
    +    def durable_append(entry) -> None:
    +        if entry.sequence == fail_at:
    +            raise OSError("injected journal failure")
    +
    +    oplog = Oplog(listener=durable_append)
    +    collection = Collection("items", oplog=oplog)
    +    collection.insert_many(
    +        [
    +            {"_id": 1, "state": "old"},
    +            {"_id": 2, "state": "old"},
    +            {"_id": 3, "state": "old"},
    +        ]
    +    )
    +    fail_at = 5
    +
    +    with pytest.raises(OSError, match="injected journal failure"):
    +        if operation == "update":
    +            collection.update_many({}, {"$set": {"state": "new"}})
    +        else:
    +            collection.delete_many({})
    +
    +    if operation == "update":
    +        assert collection.find() == [
    +            {"_id": 1, "state": "new"},
    +            {"_id": 2, "state": "old"},
    +            {"_id": 3, "state": "old"},
    +        ]
    +    else:
    +        assert collection.find() == [
    +            {"_id": 2, "state": "old"},
    +            {"_id": 3, "state": "old"},
    +        ]
    +    assert [entry.sequence for entry in oplog] == [1, 2, 3, 4]
    +    assert oplog.last_sequence == 4
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

Failure injection interrupts open, write, and fsync for insert, update, and delete; identity cases compare bool, numbers, NaN, and nested BSON; filesystem spies require directory fsync.

**Key test statement**

```python
assert collection.find() == [{"_id": True}, {"_id": 1}]
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/test_recovery.py"
    ```diff
    diff --git a/tests/test_recovery.py b/tests/test_recovery.py
    index 73dd800f38237a6aea5701b704023d0738d9c21b..7e3f65fb4a056fcb031ea79c6aab12ec53c66e50 100644
    --- a/tests/test_recovery.py
    +++ b/tests/test_recovery.py
    @@ -2,9 +2,12 @@

     from pathlib import Path

    +import pytest
    +
     from minimongodb import Database
     from minimongodb.oplog import OplogEntry
     from minimongodb.storage import Journal
    +from minimongodb.storage import journal as journal_module


     def test_restart_uses_checkpoint_then_only_newer_journal_entries(tmp_path: Path) -> None:
    @@ -41,3 +44,103 @@ def test_every_incomplete_second_frame_recovers_the_complete_prefix(
             (case / "journal.bin").write_bytes(complete[:cut])
             recovered = Database(case)
             assert recovered.get_collection("items").find() == [{"_id": 1}]
    +
    +
    +class _WriteFailingStream:
    +    def __init__(self, stream) -> None:
    +        self._stream = stream
    +
    +    def __enter__(self):
    +        self._stream.__enter__()
    +        return self
    +
    +    def __exit__(self, *args):
    +        return self._stream.__exit__(*args)
    +
    +    def write(self, data: bytes) -> int:
    +        self._stream.write(data[: len(data) // 2])
    +        self._stream.flush()
    +        raise OSError("injected journal write failure")
    +
    +    def __getattr__(self, name):
    +        return getattr(self._stream, name)
    +
    +
    +@pytest.mark.parametrize("failure_stage", ["open", "write", "fsync"])
    +@pytest.mark.parametrize("operation", ["insert", "update", "delete"])
    +def test_failed_journal_append_is_not_published_or_replayed(
    +    tmp_path: Path,
    +    monkeypatch: pytest.MonkeyPatch,
    +    failure_stage: str,
    +    operation: str,
    +) -> None:
    +    database = Database(tmp_path)
    +    items = database["items"]
    +    items.insert_one({"_id": 1, "state": "durable"})
    +    journal_path = tmp_path / "journal.bin"
    +    original_open = Path.open
    +    original_fsync = journal_module.os.fsync
    +
    +    with monkeypatch.context() as injected:
    +        if failure_stage == "open":
    +
    +            def failing_open(path, mode="r", *args, **kwargs):
    +                if path == journal_path and mode == "ab":
    +                    raise OSError("injected journal open failure")
    +                return original_open(path, mode, *args, **kwargs)
    +
    +            injected.setattr(Path, "open", failing_open)
    +        elif failure_stage == "write":
    +
    +            def write_failing_open(path, mode="r", *args, **kwargs):
    +                stream = original_open(path, mode, *args, **kwargs)
    +                if path == journal_path and mode == "ab":
    +                    return _WriteFailingStream(stream)
    +                return stream
    +
    +            injected.setattr(Path, "open", write_failing_open)
    +        else:
    +            failed = False
    +
    +            def failing_fsync(fd: int) -> None:
    +                nonlocal failed
    +                if not failed:
    +                    failed = True
    +                    raise OSError("injected journal fsync failure")
    +                original_fsync(fd)
    +
    +            injected.setattr(journal_module.os, "fsync", failing_fsync)
    +
    +        with pytest.raises(OSError, match=f"injected journal {failure_stage} failure"):
    +            if operation == "insert":
    +                items.insert_one({"_id": 2, "state": "must stay invisible"})
    +            elif operation == "update":
    +                items.update_one(
    +                    {"_id": 1},
    +                    {"$set": {"state": "must stay invisible"}},
    +                )
    +            else:
    +                items.delete_one({"_id": 1})
    +
    +    assert items.find() == [{"_id": 1, "state": "durable"}]
    +    assert [entry.sequence for entry in database.oplog] == [1]
    +    assert database.oplog.last_sequence == 1
    +
    +    failed_restart = Database(tmp_path)
    +    assert failed_restart["items"].find() == [{"_id": 1, "state": "durable"}]
    +    assert failed_restart.oplog.last_sequence == 1
    +
    +    if operation == "insert":
    +        items.insert_one({"_id": 2, "state": "retry"})
    +        expected = [
    +            {"_id": 1, "state": "durable"},
    +            {"_id": 2, "state": "retry"},
    +        ]
    +    elif operation == "update":
    +        items.update_one({"_id": 1}, {"$set": {"state": "retry"}})
    +        expected = [{"_id": 1, "state": "retry"}]
    +    else:
    +        items.delete_one({"_id": 1})
    +        expected = []
    +    assert [entry.sequence for entry in database.oplog] == [1, 2]
    +    assert Database(tmp_path)["items"].find() == expected
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

Failure injection interrupts open, write, and fsync for insert, update, and delete; identity cases compare bool, numbers, NaN, and nested BSON; filesystem spies require directory fsync.

**Key test statement**

```python
assert collection.find() == [{"_id": True}, {"_id": 1}]
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/test_storage.py"
    ```diff
    diff --git a/tests/test_storage.py b/tests/test_storage.py
    index 3c63148b6b2c94d4156021490f0f37b31c1e1380..58872eefd7eeb73d06de0454d6ab7a954025c5d5 100644
    --- a/tests/test_storage.py
    +++ b/tests/test_storage.py
    @@ -1,5 +1,6 @@
     """CRC journal framing, tail repair, and checkpoint snapshot contracts."""

    +import os
     from pathlib import Path

     import pytest
    @@ -63,3 +64,31 @@ def test_checkpoint_round_trips_tagged_object_ids(tmp_path: Path) -> None:
         }
         write_checkpoint(path, state)
         assert read_checkpoint(path) == state
    +
    +
    +def test_checkpoint_fsyncs_parent_directory_after_replace(
    +    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    +) -> None:
    +    directory_fd = 4242
    +    opened: list[tuple[Path, int]] = []
    +    fsynced: list[int] = []
    +    closed: list[int] = []
    +
    +    def record_open(path, flags):
    +        opened.append((Path(path), flags))
    +        return directory_fd
    +
    +    monkeypatch.setattr(os, "open", record_open)
    +    monkeypatch.setattr(os, "fsync", fsynced.append)
    +    monkeypatch.setattr(os, "close", closed.append)
    +
    +    write_checkpoint(tmp_path / "checkpoint.bin", {"sequence": 0, "collections": {}})
    +
    +    assert opened == [
    +        (
    +            tmp_path,
    +            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
    +        )
    +    ]
    +    assert fsynced[-1] == directory_fd
    +    assert closed == [directory_fd]
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

Failure injection interrupts open, write, and fsync for insert, update, and delete; identity cases compare bool, numbers, NaN, and nested BSON; filesystem spies require directory fsync.

**Key test statement**

```python
assert collection.find() == [{"_id": True}, {"_id": 1}]
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

Journal-first means the durable append is the commit point for each logical write. Canonical keys make index identity agree with BSON equality, and directory fsync makes rename durable.

### Why this mechanism is necessary

The first implementation exposed three crash edges: publishing before journal success, using non-canonical `_id` keys, and renaming a checkpoint without syncing its directory. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

The collection prepares new state without exposing it, appends and syncs the oplog entry, then mutates documents and indexes; failure leaves the prior visible state.

### Mechanism blocks

#### Journal-first identity boundary mechanism

The collection prepares new state without exposing it, appends and syncs the oplog entry, then mutates documents and indexes; failure leaves the prior visible state.

??? note "File diff: src/minimongodb/bson/types.py"
    ```diff
    diff --git a/src/minimongodb/bson/types.py b/src/minimongodb/bson/types.py
    index be1cb0391e3f6015d55a9d2727002de96c0f434b..6039a2f75f2cadcd4e2836a2f5ac66871f8cf3e4 100644
    --- a/src/minimongodb/bson/types.py
    +++ b/src/minimongodb/bson/types.py
    @@ -134,6 +134,26 @@ def bson_equal(left: Any, right: Any) -> bool:
         return left == right


    +def canonical_key(value: Any) -> tuple[Any, ...]:
    +    """Return a hashable key with exactly ``bson_equal`` identity semantics."""
    +
    +    tag = type_tag(value)
    +    if tag == "number":
    +        if isinstance(value, float) and isnan(value):
    +            return (tag, "nan")
    +        return (tag, value)
    +    if tag == "document":
    +        return (
    +            tag,
    +            tuple((key, canonical_key(child)) for key, child in value.items()),
    +        )
    +    if tag == "array":
    +        return (tag, tuple(canonical_key(child) for child in value))
    +    if tag == "objectId":
    +        return (tag, value.value)
    +    return (tag, value)
    +
    +
     def bson_compare(left: Any, right: Any) -> int:
         """Three-way comparison using MiniMongoDB's documented type order."""

    ```

??? note "File diff: src/minimongodb/collection.py"
    ```diff
    diff --git a/src/minimongodb/collection.py b/src/minimongodb/collection.py
    index 38b2cc8608ea0004d5942c27df0172323cc66fa4..7907fb82546093b8612abaa1db4a4ea69eab9b91 100644
    --- a/src/minimongodb/collection.py
    +++ b/src/minimongodb/collection.py
    @@ -13,6 +13,7 @@ from typing import Any, Callable, Iterable
     from minimongodb.bson import (
         CounterObjectIdGenerator,
         bson_equal,
    +    canonical_key,
         clone_document,
     )
     from minimongodb.errors import DuplicateKeyError, InvalidUpdateError
    @@ -64,28 +65,26 @@ class Collection:

         def insert_many(self, documents: Iterable[dict[str, Any]]) -> InsertManyResult:
             candidates: list[dict[str, Any]] = []
    -        pending_ids: set[Any] = set()
    +        pending_ids: set[tuple[Any, ...]] = set()
             for source in documents:
                 candidate = clone_document(source)
                 if "_id" not in candidate:
                     candidate["_id"] = self._id_generator()
                 key = candidate["_id"]
    -            try:
    -                duplicate = self._id_index.contains(key) or key in pending_ids
    -                pending_ids.add(key)
    -            except TypeError as error:
    -                raise TypeError("_id must be hashable in MiniMongoDB") from error
    +            canonical = canonical_key(key)
    +            duplicate = self._id_index.contains(key) or canonical in pending_ids
    +            pending_ids.add(canonical)
                 if duplicate:
                     raise DuplicateKeyError(f"duplicate key for _id index: {key!r}")
                 candidates.append(candidate)

    -        # Validation happens for the whole batch before the first visible write.
    +        # Validate the whole batch, then durably publish one document at a time.
             for candidate in candidates:
    -            self._documents.append(candidate)
    -            self._id_index.add(candidate)
                 self.oplog.emit(
                     self.name, "insert", candidate["_id"], clone_document(candidate)
                 )
    +            self._documents.append(candidate)
    +            self._id_index.add(candidate)
             return InsertManyResult([candidate["_id"] for candidate in candidates])

         def find(self, query: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    @@ -136,13 +135,13 @@ class Collection:
                 matched += 1
                 candidate = apply_operator_update(original, update)
                 if not bson_equal(candidate, original):
    -                self._replace_at(position, candidate)
                     self.oplog.emit(
                         self.name,
                         "update",
                         original["_id"],
                         self._post_image_update(candidate, update),
                     )
    +                self._replace_at(position, candidate)
                     modified += 1
                 if limit is not None and matched >= limit:
                     break
    @@ -160,13 +159,13 @@ class Collection:
                     candidate = replacement_document(original, replacement)
                     modified = not bson_equal(candidate, original)
                     if modified:
    -                    self._replace_at(position, candidate)
                         self.oplog.emit(
                             self.name,
                             "replace",
                             original["_id"],
                             clone_document(candidate),
                         )
    +                    self._replace_at(position, candidate)
                     return UpdateResult(1, int(modified))
             return UpdateResult(0, 0)

    @@ -178,15 +177,16 @@ class Collection:

         def _delete(self, query: dict[str, Any], *, limit: int | None) -> DeleteResult:
             deleted = 0
    -        kept: list[dict[str, Any]] = []
    -        for document in self._documents:
    +        position = 0
    +        while position < len(self._documents):
    +            document = self._documents[position]
                 if matches(document, query) and (limit is None or deleted < limit):
    -                self._id_index.remove(document["_id"])
                     self.oplog.emit(self.name, "delete", document["_id"])
    +                self._id_index.remove(document["_id"])
    +                self._documents.pop(position)
                     deleted += 1
                 else:
    -                kept.append(document)
    -        self._documents = kept
    +                position += 1
             return DeleteResult(deleted)

         def _replace_at(self, position: int, document: dict[str, Any]) -> None:
    ```

??? note "File diff: src/minimongodb/index/id_index.py"
    ```diff
    diff --git a/src/minimongodb/index/id_index.py b/src/minimongodb/index/id_index.py
    index 0cf0e02a7665b4e9768be51e2eacaa3d1d253201..ce512aeff2f2953345feea81256d61c8bb039961 100644
    --- a/src/minimongodb/index/id_index.py
    +++ b/src/minimongodb/index/id_index.py
    @@ -4,6 +4,7 @@ from __future__ import annotations

     from typing import Any

    +from minimongodb.bson import canonical_key
     from minimongodb.errors import DuplicateKeyError


    @@ -11,31 +12,29 @@ class IdIndex:
         """Unique key-to-document map used for validation and direct lookup."""

         def __init__(self) -> None:
    -        self._documents: dict[Any, dict[str, Any]] = {}
    +        self._documents: dict[tuple[Any, ...], dict[str, Any]] = {}

         def add(self, document: dict[str, Any]) -> None:
    -        key = document["_id"]
    -        try:
    -            if key in self._documents:
    -                raise DuplicateKeyError(f"duplicate key for _id index: {key!r}")
    -            self._documents[key] = document
    -        except TypeError as error:
    -            raise TypeError("_id must be hashable in MiniMongoDB") from error
    +        value = document["_id"]
    +        key = canonical_key(value)
    +        if key in self._documents:
    +            raise DuplicateKeyError(f"duplicate key for _id index: {value!r}")
    +        self._documents[key] = document

         def remove(self, key: Any) -> None:
    -        self._documents.pop(key)
    +        self._documents.pop(canonical_key(key))

         def replace(self, key: Any, document: dict[str, Any]) -> None:
    -        self._documents[key] = document
    +        self._documents[canonical_key(key)] = document

         def get(self, key: Any) -> dict[str, Any] | None:
             try:
    -            return self._documents.get(key)
    +            return self._documents.get(canonical_key(key))
             except TypeError:
                 return None

         def contains(self, key: Any) -> bool:
             try:
    -            return key in self._documents
    +            return canonical_key(key) in self._documents
             except TypeError:
                 return False
    ```

??? note "File diff: src/minimongodb/oplog/entry.py"
    ```diff
    diff --git a/src/minimongodb/oplog/entry.py b/src/minimongodb/oplog/entry.py
    index 69eb2f6e91ee89ff55fb356c66979a3c77bfedba..f60a5c6ce7f8d7f2123ef766bc43796b831f51fa 100644
    --- a/src/minimongodb/oplog/entry.py
    +++ b/src/minimongodb/oplog/entry.py
    @@ -61,9 +61,9 @@ class Oplog:
                 key=key,
                 payload=clone_document(payload) if payload is not None else None,
             )
    -        self._next_sequence += 1
    -        self._entries.append(entry)
             if self._listener is not None:
    -            # Persistence observes only complete in-memory mutations.
    +            # Durable acceptance is the publication boundary.
                 self._listener(entry)
    +        self._entries.append(entry)
    +        self._next_sequence += 1
             return entry
    ```

??? note "File diff: src/minimongodb/storage/checkpoint.py"
    ```diff
    diff --git a/src/minimongodb/storage/checkpoint.py b/src/minimongodb/storage/checkpoint.py
    index ed2a791950bf5d3bc7801342cc2903baad8dce48..6f0de4c7f2bdac57bf6da49920e55d9291415a76 100644
    --- a/src/minimongodb/storage/checkpoint.py
    +++ b/src/minimongodb/storage/checkpoint.py
    @@ -19,6 +19,12 @@ def write_checkpoint(path: str | Path, state: dict[str, Any]) -> None:
             stream.flush()
             os.fsync(stream.fileno())
         os.replace(temporary, destination)
    +    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    +    directory_fd = os.open(destination.parent, flags)
    +    try:
    +        os.fsync(directory_fd)
    +    finally:
    +        os.close(directory_fd)


     def read_checkpoint(path: str | Path) -> dict[str, Any] | None:
    ```

??? note "File diff: src/minimongodb/storage/journal.py"
    ```diff
    diff --git a/src/minimongodb/storage/journal.py b/src/minimongodb/storage/journal.py
    index 142911435cc0ed6269cba8860c487037825a2bcf..7668a4d28b55ff44a0684e95d0ebbbf173c17722 100644
    --- a/src/minimongodb/storage/journal.py
    +++ b/src/minimongodb/storage/journal.py
    @@ -24,10 +24,34 @@ class Journal:
             payload = encode_entry(entry)
             frame = _U32.pack(len(payload)) + payload + _U32.pack(zlib.crc32(payload))
             self.path.parent.mkdir(parents=True, exist_ok=True)
    -        with self.path.open("ab") as stream:
    -            stream.write(frame)
    -            stream.flush()
    -            os.fsync(stream.fileno())
    +        previous_size = self.path.stat().st_size if self.path.exists() else 0
    +        try:
    +            with self.path.open("ab") as stream:
    +                written = stream.write(frame)
    +                if written != len(frame):
    +                    raise OSError(
    +                        f"short journal write: expected {len(frame)}, wrote {written}"
    +                    )
    +                stream.flush()
    +                os.fsync(stream.fileno())
    +        except Exception:
    +            self._rollback_append(previous_size)
    +            raise
    +
    +    def _rollback_append(self, previous_size: int) -> None:
    +        """Best-effort removal of bytes from an append that reported failure."""
    +
    +        if not self.path.exists():
    +            return
    +        try:
    +            with self.path.open("r+b") as stream:
    +                stream.truncate(previous_size)
    +                stream.flush()
    +                os.fsync(stream.fileno())
    +        except OSError:
    +            # Preserve the original append error; restart tail repair remains
    +            # the final defense if the cleanup fsync also fails.
    +            pass

         def read_entries(self, *, repair: bool = True) -> list[OplogEntry]:
             if not self.path.exists():
    ```

**What it is and why it appears**

Journal-first means the durable append is the commit point for each logical write. Canonical keys make index identity agree with BSON equality, and directory fsync makes rename durable.

**Runtime role**

The collection prepares new state without exposing it, appends and syncs the oplog entry, then mutates documents and indexes; failure leaves the prior visible state.

**Statement understanding**

Ordering is the proof: moving publication before append can acknowledge state that restart cannot reconstruct.

#### Package, fixture, and project support

Keep exports, test corpora, dependencies, and the runtime environment reproducible.

??? note "Supporting file diffs (1 file)"
    **`src/minimongodb/bson/__init__.py`**

    ```diff
    diff --git a/src/minimongodb/bson/__init__.py b/src/minimongodb/bson/__init__.py
    index c4c50774534974cd8976210206fbd8de6c68a844..ab6f667d09967caf4024bf2338482f4439350f30 100644
    --- a/src/minimongodb/bson/__init__.py
    +++ b/src/minimongodb/bson/__init__.py
    @@ -6,6 +6,7 @@ from minimongodb.bson.types import (
         ObjectId,
         bson_compare,
         bson_equal,
    +    canonical_key,
         clone_document,
         type_tag,
     )
    @@ -16,6 +17,7 @@ __all__ = [
         "ObjectId",
         "bson_compare",
         "bson_equal",
    +    "canonical_key",
         "clone_document",
         "get_path",
         "set_path",
    ```


### Verification evidence

Run `uv run pytest -q $(cat journey/stages/05-journal-first-identity/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

Ordering is the proof: moving publication before append can acknowledge state that restart cannot reconstruct.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 5](https://github.com/system-in-miniature/mini-mongodb/blob/main/docs/tutorial/05-durability.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-mongodb/blob/main/journey/stages/05-journal-first-identity/stage.patch)
