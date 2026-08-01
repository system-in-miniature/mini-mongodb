# Stage 04 · CRUD、更新与恢复闭环

### 目标

实现CRUD、更新与恢复闭环，并能从可执行反例、运行时状态与关键语句解释其边界。

??? note "交付文件"
    - `src/minimongodb/__init__.py`
    - `src/minimongodb/aggregate/__init__.py`
    - `src/minimongodb/collection.py`
    - `src/minimongodb/database.py`
    - `src/minimongodb/index/__init__.py`
    - `src/minimongodb/index/id_index.py`
    - `src/minimongodb/oplog/replay.py`
    - `src/minimongodb/plan/__init__.py`
    - `src/minimongodb/update/__init__.py`
    - `src/minimongodb/update/operators.py`
    - `tests/test_crud.py`
    - `tests/test_oplog.py`
    - `tests/test_recovery.py`
    - `tests/test_update.py`

### 当前遇到的问题

值与存储原语还不是数据库：必须由一个所有者协调身份、匹配、修改、Oplog 后镜像、Checkpoint 与启动回放。

### 测试契约

#### 先看会坏在哪里

测试覆盖重复与不可变 `_id`、部分批次、返回值副本、点路径更新算子、幂等回放及 Checkpoint 加 Journal 重启。

??? note "文件差异：tests/test_crud.py"
    ```diff
    diff --git a/tests/test_crud.py b/tests/test_crud.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..6c30385f4990cdd155e445a456cfe1044589f75f
    --- /dev/null
    +++ b/tests/test_crud.py
    @@ -0,0 +1,45 @@
    +"""Public CRUD contract and automatic unique ``_id`` index."""
    +
    +import pytest
    +
    +from minimongodb import Collection, CounterObjectIdGenerator, ObjectId
    +from minimongodb.errors import DuplicateKeyError
    +
    +
    +def test_insert_find_and_copy_isolation() -> None:
    +    collection = Collection("people", id_generator=CounterObjectIdGenerator(10))
    +    source = {"name": "Ada", "profile": {"city": "London"}}
    +    result = collection.insert_one(source)
    +
    +    assert result.inserted_id == ObjectId(10)
    +    assert "_id" not in source
    +    found = collection.find({"name": "Ada"})
    +    assert found == [
    +        {"name": "Ada", "profile": {"city": "London"}, "_id": ObjectId(10)}
    +    ]
    +    found[0]["profile"]["city"] = "changed outside"
    +    assert collection.find_one({"_id": ObjectId(10)})["profile"]["city"] == "London"
    +
    +
    +def test_insert_many_uses_counter_in_input_order() -> None:
    +    collection = Collection(id_generator=CounterObjectIdGenerator(1))
    +    result = collection.insert_many([{"n": 1}, {"n": 2}])
    +    assert result.inserted_ids == [ObjectId(1), ObjectId(2)]
    +
    +
    +def test_id_index_rejects_duplicate_key_without_partial_insert_many() -> None:
    +    collection = Collection()
    +    collection.insert_one({"_id": "same", "n": 1})
    +    with pytest.raises(DuplicateKeyError):
    +        collection.insert_many([{"_id": "new"}, {"_id": "same"}])
    +    assert collection.find({}) == [{"_id": "same", "n": 1}]
    +
    +
    +def test_delete_one_and_many_report_deleted_counts() -> None:
    +    collection = Collection()
    +    collection.insert_many(
    +        [{"_id": 1, "kind": "x"}, {"_id": 2, "kind": "x"}, {"_id": 3, "kind": "y"}]
    +    )
    +    assert collection.delete_one({"kind": "x"}).deleted_count == 1
    +    assert collection.delete_many({"kind": "x"}).deleted_count == 1
    +    assert [doc["_id"] for doc in collection.find()] == [3]
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

测试覆盖重复与不可变 `_id`、部分批次、返回值副本、点路径更新算子、幂等回放及 Checkpoint 加 Journal 重启。

**关键测试语句**

```python
assert entry.payload is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/test_oplog.py"
    ```diff
    diff --git a/tests/test_oplog.py b/tests/test_oplog.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..d19f44214c005f792ae2ebc7c21fb28b69b37a51
    --- /dev/null
    +++ b/tests/test_oplog.py
    @@ -0,0 +1,64 @@
    +"""Oplog entries are deterministic state assignments, not user commands."""
    +
    +from minimongodb import Collection
    +from minimongodb.oplog import Oplog, replay
    +
    +
    +def test_writes_emit_ordered_entries_per_affected_document() -> None:
    +    collection = Collection("items")
    +    collection.insert_many([{"_id": 1, "n": 1}, {"_id": 2, "n": 1}])
    +    collection.update_many({}, {"$inc": {"n": 1}})
    +    collection.delete_one({"_id": 1})
    +
    +    assert [entry.sequence for entry in collection.oplog] == [1, 2, 3, 4, 5]
    +    assert [entry.operation for entry in collection.oplog] == [
    +        "insert",
    +        "insert",
    +        "update",
    +        "update",
    +        "delete",
    +    ]
    +
    +
    +def test_inc_is_rewritten_to_an_idempotent_set_result() -> None:
    +    collection = Collection("counters")
    +    collection.insert_one({"_id": "visits", "count": 2})
    +    collection.update_one({"_id": "visits"}, {"$inc": {"count": 3}})
    +
    +    entry = list(collection.oplog)[-1]
    +    assert entry.operation == "update"
    +    assert entry.payload == {"$set": {"count": 5}}
    +    assert "$inc" not in entry.payload
    +
    +
    +def test_replaying_the_same_oplog_twice_has_the_same_result() -> None:
    +    source = Collection("people")
    +    source.insert_many([{"_id": 1, "n": 1}, {"_id": 2, "n": 10}])
    +    source.update_one({"_id": 1}, {"$inc": {"n": 2}})
    +    source.replace_one({"_id": 2}, {"n": 11})
    +    source.delete_one({"_id": 2})
    +
    +    target = Collection("people", oplog=Oplog())
    +    replay(source.oplog, target)
    +    once = target.find()
    +    replay(source.oplog, target)
    +
    +    assert target.find() == once == [{"_id": 1, "n": 3}]
    +    # Recovery actions must not recursively create a second oplog.
    +    assert list(target.oplog) == []
    +
    +
    +def test_post_image_keeps_only_the_final_state_for_a_repeated_path() -> None:
    +    source = Collection("items")
    +    source.insert_one({"_id": 1, "value": "old"})
    +    source.update_one(
    +        {"_id": 1},
    +        {"$unset": {"value": ""}, "$set": {"value": "final"}},
    +    )
    +    entry = list(source.oplog)[-1]
    +    assert entry.payload == {"$set": {"value": "final"}}
    +
    +    target = Collection("items", oplog=Oplog())
    +    replay(source.oplog, target)
    +    replay(source.oplog, target)
    +    assert target.find_one({"_id": 1})["value"] == "final"
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

测试覆盖重复与不可变 `_id`、部分批次、返回值副本、点路径更新算子、幂等回放及 Checkpoint 加 Journal 重启。

**关键测试语句**

```python
assert entry.payload is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/test_recovery.py"
    ```diff
    diff --git a/tests/test_recovery.py b/tests/test_recovery.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..73dd800f38237a6aea5701b704023d0738d9c21b
    --- /dev/null
    +++ b/tests/test_recovery.py
    @@ -0,0 +1,43 @@
    +"""Checkpoint + valid journal prefix reconstructs deterministic state."""
    +
    +from pathlib import Path
    +
    +from minimongodb import Database
    +from minimongodb.oplog import OplogEntry
    +from minimongodb.storage import Journal
    +
    +
    +def test_restart_uses_checkpoint_then_only_newer_journal_entries(tmp_path: Path) -> None:
    +    database = Database(tmp_path)
    +    items = database.get_collection("items")
    +    items.insert_one({"_id": 1, "value": "checkpoint"})
    +    database.checkpoint()
    +    items.insert_one({"_id": 2, "value": "journal"})
    +
    +    recovered = Database(tmp_path)
    +    assert recovered.get_collection("items").find() == [
    +        {"_id": 1, "value": "checkpoint"},
    +        {"_id": 2, "value": "journal"},
    +    ]
    +    # Starting yet again proves startup replay itself did not append records.
    +    assert Database(tmp_path).get_collection("items").find() == recovered.get_collection(
    +        "items"
    +    ).find()
    +
    +
    +def test_every_incomplete_second_frame_recovers_the_complete_prefix(
    +    tmp_path: Path,
    +) -> None:
    +    template = tmp_path / "template.bin"
    +    journal = Journal(template)
    +    journal.append(OplogEntry(1, "items", "insert", 1, {"_id": 1}))
    +    first_size = template.stat().st_size
    +    journal.append(OplogEntry(2, "items", "insert", 2, {"_id": 2}))
    +    complete = template.read_bytes()
    +
    +    for cut in range(first_size, len(complete)):
    +        case = tmp_path / f"cut-{cut}"
    +        case.mkdir()
    +        (case / "journal.bin").write_bytes(complete[:cut])
    +        recovered = Database(case)
    +        assert recovered.get_collection("items").find() == [{"_id": 1}]
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

测试覆盖重复与不可变 `_id`、部分批次、返回值副本、点路径更新算子、幂等回放及 Checkpoint 加 Journal 重启。

**关键测试语句**

```python
assert entry.payload is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/test_update.py"
    ```diff
    diff --git a/tests/test_update.py b/tests/test_update.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..2a55a52dd7d81f7b0fc319a501798893258188f1
    --- /dev/null
    +++ b/tests/test_update.py
    @@ -0,0 +1,84 @@
    +"""Update routing, dotted operators, and immutable identity."""
    +
    +import pytest
    +
    +from minimongodb import Collection
    +from minimongodb.errors import ImmutableIdError, InvalidUpdateError
    +
    +
    +def test_set_unset_and_inc_follow_dotted_paths() -> None:
    +    collection = Collection()
    +    collection.insert_one({"_id": 1, "stats": {"count": 2}, "old": True})
    +    result = collection.update_one(
    +        {"_id": 1},
    +        {"$set": {"stats.label": "ok"}, "$inc": {"stats.count": 3}, "$unset": {"old": ""}},
    +    )
    +    assert (result.matched_count, result.modified_count) == (1, 1)
    +    assert collection.find_one({"_id": 1}) == {
    +        "_id": 1,
    +        "stats": {"count": 5, "label": "ok"},
    +    }
    +
    +
    +def test_push_and_pull_use_array_element_matching() -> None:
    +    collection = Collection()
    +    collection.insert_one({"_id": 1, "tags": ["db"], "scores": [2, 8, 3]})
    +    collection.update_one(
    +        {"_id": 1},
    +        {"$push": {"tags": "python"}, "$pull": {"scores": {"$gt": 5}}},
    +    )
    +    assert collection.find_one({"_id": 1}) == {
    +        "_id": 1,
    +        "tags": ["db", "python"],
    +        "scores": [2, 3],
    +    }
    +
    +
    +def test_update_many_counts_matches_and_actual_modifications() -> None:
    +    collection = Collection()
    +    collection.insert_many([{"_id": 1, "x": 1}, {"_id": 2, "x": 1}])
    +    result = collection.update_many({"x": 1}, {"$set": {"x": 1}})
    +    assert (result.matched_count, result.modified_count) == (2, 0)
    +
    +
    +def test_replace_document_preserves_id_when_omitted() -> None:
    +    collection = Collection()
    +    collection.insert_one({"_id": 1, "old": True})
    +    result = collection.replace_one({"_id": 1}, {"new": True})
    +    assert (result.matched_count, result.modified_count) == (1, 1)
    +    assert collection.find_one() == {"new": True, "_id": 1}
    +
    +
    +@pytest.mark.parametrize(
    +    "operation",
    +    [
    +        lambda c: c.update_one({"_id": 1}, {"$set": {"_id": 2}}),
    +        lambda c: c.update_one({"_id": 1}, {"$unset": {"_id": ""}}),
    +        lambda c: c.replace_one({"_id": 1}, {"_id": 2}),
    +    ],
    +)
    +def test_id_is_immutable(operation) -> None:
    +    collection = Collection()
    +    collection.insert_one({"_id": 1})
    +    with pytest.raises(ImmutableIdError):
    +        operation(collection)
    +
    +
    +def test_operator_and_replacement_syntax_cannot_be_mixed() -> None:
    +    collection = Collection()
    +    collection.insert_one({"_id": 1})
    +    with pytest.raises(InvalidUpdateError):
    +        collection.update_one({"_id": 1}, {"$set": {"x": 1}, "plain": 2})
    +
    +
    +def test_update_values_are_validated_and_copied_before_storage() -> None:
    +    collection = Collection()
    +    collection.insert_one({"_id": 1, "items": []})
    +    caller_owned = {"nested": [1]}
    +    collection.update_one({"_id": 1}, {"$set": {"value": caller_owned}})
    +    caller_owned["nested"].append(2)
    +    assert collection.find_one({"_id": 1})["value"] == {"nested": [1]}
    +
    +    with pytest.raises(TypeError, match="unsupported BSON value"):
    +        collection.update_one({"_id": 1}, {"$push": {"items": {1, 2}}})
    +    assert collection.find_one({"_id": 1})["items"] == []
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

测试覆盖重复与不可变 `_id`、部分批次、返回值副本、点路径更新算子、幂等回放及 Checkpoint 加 Journal 重启。

**关键测试语句**

```python
assert entry.payload is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

Collection 拥有活文档与索引；Database 拥有命名集合与持久性。算子更新在写日志前变成最终状态后镜像。

### 为什么需要这个机制

值与存储原语还不是数据库：必须由一个所有者协调身份、匹配、修改、Oplog 后镜像、Checkpoint 与启动回放。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

写入先校验候选状态、分配序号、记录持久转换，再发布受控状态。启动时载入 Checkpoint，只回放更新的 Entry。

### 机制板块

#### CRUD、更新与恢复闭环机制

写入先校验候选状态、分配序号、记录持久转换，再发布受控状态。启动时载入 Checkpoint，只回放更新的 Entry。

??? note "文件差异：src/minimongodb/aggregate/__init__.py"
    ```diff
    diff --git a/src/minimongodb/aggregate/__init__.py b/src/minimongodb/aggregate/__init__.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..a346aa409dfc011c4fcd58cc17d7b2b02882b265
    --- /dev/null
    +++ b/src/minimongodb/aggregate/__init__.py
    @@ -0,0 +1,7 @@
    +"""M2 placeholder for ``$match/$project/$group/$sort/$limit`` pipelines.
    +
    +The future package will model aggregation stages as a pull-based operator
    +stream so it can be compared directly with MiniPostgres' relational execution
    +operators.  M1 does not accept aggregation syntax or pretend a list
    +comprehension is a complete pipeline.
    +"""
    ```

??? note "文件差异：src/minimongodb/collection.py"
    ```diff
    diff --git a/src/minimongodb/collection.py b/src/minimongodb/collection.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..38b2cc8608ea0004d5942c27df0172323cc66fa4
    --- /dev/null
    +++ b/src/minimongodb/collection.py
    @@ -0,0 +1,246 @@
    +"""Collection is the M1 convergence layer for matching, mutation, and indexing.
    +
    +Documents are kept in insertion order for deterministic teaching output.  The
    +separate ``IdIndex`` supplies uniqueness and direct identity lookup; M2 will
    +add secondary indexes and planning without changing this public CRUD surface.
    +"""
    +
    +from __future__ import annotations
    +
    +from dataclasses import dataclass
    +from typing import Any, Callable, Iterable
    +
    +from minimongodb.bson import (
    +    CounterObjectIdGenerator,
    +    bson_equal,
    +    clone_document,
    +)
    +from minimongodb.errors import DuplicateKeyError, InvalidUpdateError
    +from minimongodb.index import IdIndex
    +from minimongodb.oplog.entry import Oplog, OplogEntry
    +from minimongodb.query import matches
    +from minimongodb.update import apply_operator_update, replacement_document
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class InsertOneResult:
    +    inserted_id: Any
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class InsertManyResult:
    +    inserted_ids: list[Any]
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class UpdateResult:
    +    matched_count: int
    +    modified_count: int
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class DeleteResult:
    +    deleted_count: int
    +
    +
    +class Collection:
    +    """A deterministic, single-writer collection with a unique ``_id`` index."""
    +
    +    def __init__(
    +        self,
    +        name: str = "default",
    +        *,
    +        id_generator: Callable[[], Any] | None = None,
    +        oplog: Oplog | None = None,
    +    ) -> None:
    +        self.name = name
    +        self._id_generator = id_generator or CounterObjectIdGenerator()
    +        self._documents: list[dict[str, Any]] = []
    +        self._id_index = IdIndex()
    +        self.oplog = oplog if oplog is not None else Oplog()
    +
    +    def insert_one(self, document: dict[str, Any]) -> InsertOneResult:
    +        return InsertOneResult(self.insert_many([document]).inserted_ids[0])
    +
    +    def insert_many(self, documents: Iterable[dict[str, Any]]) -> InsertManyResult:
    +        candidates: list[dict[str, Any]] = []
    +        pending_ids: set[Any] = set()
    +        for source in documents:
    +            candidate = clone_document(source)
    +            if "_id" not in candidate:
    +                candidate["_id"] = self._id_generator()
    +            key = candidate["_id"]
    +            try:
    +                duplicate = self._id_index.contains(key) or key in pending_ids
    +                pending_ids.add(key)
    +            except TypeError as error:
    +                raise TypeError("_id must be hashable in MiniMongoDB") from error
    +            if duplicate:
    +                raise DuplicateKeyError(f"duplicate key for _id index: {key!r}")
    +            candidates.append(candidate)
    +
    +        # Validation happens for the whole batch before the first visible write.
    +        for candidate in candidates:
    +            self._documents.append(candidate)
    +            self._id_index.add(candidate)
    +            self.oplog.emit(
    +                self.name, "insert", candidate["_id"], clone_document(candidate)
    +            )
    +        return InsertManyResult([candidate["_id"] for candidate in candidates])
    +
    +    def find(self, query: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    +        return [
    +            clone_document(document)
    +            for document in self._documents
    +            if matches(document, query)
    +        ]
    +
    +    def find_one(self, query: dict[str, Any] | None = None) -> dict[str, Any] | None:
    +        for document in self._documents:
    +            if matches(document, query):
    +                return clone_document(document)
    +        return None
    +
    +    def count_documents(self, query: dict[str, Any] | None = None) -> int:
    +        return sum(matches(document, query) for document in self._documents)
    +
    +    def update_one(
    +        self, query: dict[str, Any], update: dict[str, Any]
    +    ) -> UpdateResult:
    +        return self._update(query, update, limit=1)
    +
    +    def update_many(
    +        self, query: dict[str, Any], update: dict[str, Any]
    +    ) -> UpdateResult:
    +        return self._update(query, update, limit=None)
    +
    +    def _update(
    +        self,
    +        query: dict[str, Any],
    +        update: dict[str, Any],
    +        *,
    +        limit: int | None,
    +    ) -> UpdateResult:
    +        if not isinstance(update, dict) or not update:
    +            raise InvalidUpdateError("update must be a non-empty document")
    +        has_operator = [key.startswith("$") for key in update]
    +        if not all(has_operator):
    +            if any(has_operator):
    +                raise InvalidUpdateError("cannot mix operator and replacement syntax")
    +            raise InvalidUpdateError("use replace_one for a replacement document")
    +
    +        matched = modified = 0
    +        for position, original in enumerate(list(self._documents)):
    +            if not matches(original, query):
    +                continue
    +            matched += 1
    +            candidate = apply_operator_update(original, update)
    +            if not bson_equal(candidate, original):
    +                self._replace_at(position, candidate)
    +                self.oplog.emit(
    +                    self.name,
    +                    "update",
    +                    original["_id"],
    +                    self._post_image_update(candidate, update),
    +                )
    +                modified += 1
    +            if limit is not None and matched >= limit:
    +                break
    +        return UpdateResult(matched, modified)
    +
    +    def replace_one(
    +        self, query: dict[str, Any], replacement: dict[str, Any]
    +    ) -> UpdateResult:
    +        if not isinstance(replacement, dict) or not replacement:
    +            raise InvalidUpdateError("replacement must be a non-empty document")
    +        if any(key.startswith("$") for key in replacement):
    +            raise InvalidUpdateError("replace_one requires a replacement document")
    +        for position, original in enumerate(self._documents):
    +            if matches(original, query):
    +                candidate = replacement_document(original, replacement)
    +                modified = not bson_equal(candidate, original)
    +                if modified:
    +                    self._replace_at(position, candidate)
    +                    self.oplog.emit(
    +                        self.name,
    +                        "replace",
    +                        original["_id"],
    +                        clone_document(candidate),
    +                    )
    +                return UpdateResult(1, int(modified))
    +        return UpdateResult(0, 0)
    +
    +    def delete_one(self, query: dict[str, Any]) -> DeleteResult:
    +        return self._delete(query, limit=1)
    +
    +    def delete_many(self, query: dict[str, Any]) -> DeleteResult:
    +        return self._delete(query, limit=None)
    +
    +    def _delete(self, query: dict[str, Any], *, limit: int | None) -> DeleteResult:
    +        deleted = 0
    +        kept: list[dict[str, Any]] = []
    +        for document in self._documents:
    +            if matches(document, query) and (limit is None or deleted < limit):
    +                self._id_index.remove(document["_id"])
    +                self.oplog.emit(self.name, "delete", document["_id"])
    +                deleted += 1
    +            else:
    +                kept.append(document)
    +        self._documents = kept
    +        return DeleteResult(deleted)
    +
    +    def _replace_at(self, position: int, document: dict[str, Any]) -> None:
    +        key = self._documents[position]["_id"]
    +        self._documents[position] = document
    +        self._id_index.replace(key, document)
    +
    +    @staticmethod
    +    def _post_image_update(
    +        candidate: dict[str, Any], requested_update: dict[str, Any]
    +    ) -> dict[str, Any]:
    +        """Rewrite action operators to idempotent final path assignments."""
    +
    +        from minimongodb.bson import MISSING, get_path
    +
    +        set_values: dict[str, Any] = {}
    +        unset_values: dict[str, str] = {}
    +        for operand in requested_update.values():
    +            for path in operand:
    +                value = get_path(candidate, path)
    +                if value is MISSING:
    +                    unset_values[path] = ""
    +                else:
    +                    set_values[path] = value
    +        payload: dict[str, Any] = {}
    +        if set_values:
    +            payload["$set"] = set_values
    +        if unset_values:
    +            payload["$unset"] = unset_values
    +        return payload
    +
    +    def _apply_oplog_entry(self, entry: OplogEntry) -> None:
    +        """Recovery-only mutation path; deliberately emits no recursive log."""
    +
    +        existing = self._id_index.get(entry.key)
    +        if entry.operation in {"insert", "replace"}:
    +            assert entry.payload is not None
    +            candidate = clone_document(entry.payload)
    +            if existing is None:
    +                self._documents.append(candidate)
    +                self._id_index.add(candidate)
    +            else:
    +                position = self._documents.index(existing)
    +                self._replace_at(position, candidate)
    +        elif entry.operation == "update":
    +            if existing is None:
    +                return
    +            assert entry.payload is not None
    +            position = self._documents.index(existing)
    +            candidate = apply_operator_update(existing, entry.payload)
    +            self._replace_at(position, candidate)
    +        elif entry.operation == "delete":
    +            if existing is not None:
    +                self._documents.remove(existing)
    +                self._id_index.remove(entry.key)
    +        else:
    +            raise ValueError(f"unknown oplog operation: {entry.operation}")
    ```

??? note "文件差异：src/minimongodb/database.py"
    ```diff
    diff --git a/src/minimongodb/database.py b/src/minimongodb/database.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..0a717669bc1207005dce8f5a79cd305c66f86945
    --- /dev/null
    +++ b/src/minimongodb/database.py
    @@ -0,0 +1,113 @@
    +"""Database wires collections to one durable oplog and startup recovery."""
    +
    +from __future__ import annotations
    +
    +from pathlib import Path
    +from typing import Any
    +
    +from minimongodb.bson import CounterObjectIdGenerator, ObjectId
    +from minimongodb.collection import Collection
    +from minimongodb.oplog import Oplog, OplogEntry, replay
    +from minimongodb.storage import Journal, load_recovery_state, write_checkpoint
    +
    +
    +def _object_id_values(value: Any):
    +    if isinstance(value, ObjectId):
    +        yield value.value
    +    elif isinstance(value, dict):
    +        for child in value.values():
    +            yield from _object_id_values(child)
    +    elif isinstance(value, list):
    +        for child in value:
    +            yield from _object_id_values(child)
    +
    +
    +class Database:
    +    """Persistent single-writer database rooted at one explicit directory."""
    +
    +    def __init__(self, directory: str | Path) -> None:
    +        self.directory = Path(directory)
    +        self.directory.mkdir(parents=True, exist_ok=True)
    +        recovery = load_recovery_state(self.directory)
    +        highest_sequence = max(
    +            [recovery.checkpoint_sequence]
    +            + [entry.sequence for entry in recovery.journal_entries]
    +        )
    +        id_values = [
    +            value
    +            for documents in recovery.collections.values()
    +            for document in documents
    +            for value in _object_id_values(document.get("_id"))
    +        ]
    +        id_values.extend(
    +            value
    +            for entry in recovery.journal_entries
    +            for value in _object_id_values(entry.key)
    +        )
    +        self._id_generator = CounterObjectIdGenerator(max(id_values, default=0) + 1)
    +        self._journal = Journal(self.directory / "journal.bin")
    +        self.oplog = Oplog(
    +            start_sequence=highest_sequence + 1,
    +            listener=self._journal.append,
    +        )
    +        names = set(recovery.collections)
    +        names.update(entry.collection for entry in recovery.journal_entries)
    +        self._collections = {
    +            name: Collection(
    +                name,
    +                id_generator=self._id_generator,
    +                oplog=self.oplog,
    +            )
    +            for name in sorted(names)
    +        }
    +        for name, documents in recovery.collections.items():
    +            collection = self._collections[name]
    +            for document in documents:
    +                collection._apply_oplog_entry(
    +                    OplogEntry(0, name, "insert", document["_id"], document)
    +                )
    +        replay(
    +            recovery.journal_entries,
    +            self._collections,
    +            after_sequence=recovery.checkpoint_sequence,
    +        )
    +
    +    def get_collection(self, name: str) -> Collection:
    +        if name not in self._collections:
    +            self._collections[name] = Collection(
    +                name,
    +                id_generator=self._id_generator,
    +                oplog=self.oplog,
    +            )
    +        return self._collections[name]
    +
    +    def __getitem__(self, name: str) -> Collection:
    +        return self.get_collection(name)
    +
    +    def checkpoint(self) -> None:
    +        """Persist a snapshot tagged with the latest durable oplog sequence."""
    +
    +        write_checkpoint(
    +            self.directory / "checkpoint.bin",
    +            {
    +                "sequence": self.oplog.last_sequence,
    +                "collections": {
    +                    name: collection.find()
    +                    for name, collection in sorted(self._collections.items())
    +                },
    +            },
    +        )
    +
    +    def inject_journal_tail_truncation(self, byte_count: int) -> int:
    +        """Teaching fault injector: remove bytes as if a frame write crashed."""
    +
    +        if isinstance(byte_count, bool) or not isinstance(byte_count, int):
    +            raise TypeError("byte_count must be an integer")
    +        if byte_count <= 0:
    +            raise ValueError("byte_count must be positive")
    +        path = self.directory / "journal.bin"
    +        size = path.stat().st_size
    +        new_size = max(0, size - byte_count)
    +        with path.open("r+b") as stream:
    +            stream.truncate(new_size)
    +        return new_size
    ```

??? note "文件差异：src/minimongodb/index/id_index.py"
    ```diff
    diff --git a/src/minimongodb/index/id_index.py b/src/minimongodb/index/id_index.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..0cf0e02a7665b4e9768be51e2eacaa3d1d253201
    --- /dev/null
    +++ b/src/minimongodb/index/id_index.py
    @@ -0,0 +1,41 @@
    +"""A direct map models MongoDB's automatically-created unique ``_id`` index."""
    +
    +from __future__ import annotations
    +
    +from typing import Any
    +
    +from minimongodb.errors import DuplicateKeyError
    +
    +
    +class IdIndex:
    +    """Unique key-to-document map used for validation and direct lookup."""
    +
    +    def __init__(self) -> None:
    +        self._documents: dict[Any, dict[str, Any]] = {}
    +
    +    def add(self, document: dict[str, Any]) -> None:
    +        key = document["_id"]
    +        try:
    +            if key in self._documents:
    +                raise DuplicateKeyError(f"duplicate key for _id index: {key!r}")
    +            self._documents[key] = document
    +        except TypeError as error:
    +            raise TypeError("_id must be hashable in MiniMongoDB") from error
    +
    +    def remove(self, key: Any) -> None:
    +        self._documents.pop(key)
    +
    +    def replace(self, key: Any, document: dict[str, Any]) -> None:
    +        self._documents[key] = document
    +
    +    def get(self, key: Any) -> dict[str, Any] | None:
    +        try:
    +            return self._documents.get(key)
    +        except TypeError:
    +            return None
    +
    +    def contains(self, key: Any) -> bool:
    +        try:
    +            return key in self._documents
    +        except TypeError:
    +            return False
    ```

??? note "文件差异：src/minimongodb/oplog/replay.py"
    ```diff
    diff --git a/src/minimongodb/oplog/replay.py b/src/minimongodb/oplog/replay.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..fd3daaab9be28627085bce16601e3715bb44b53e
    --- /dev/null
    +++ b/src/minimongodb/oplog/replay.py
    @@ -0,0 +1,30 @@
    +"""Idempotent application of oplog post-images to collections."""
    +
    +from __future__ import annotations
    +
    +from collections.abc import Iterable, Mapping
    +
    +from minimongodb.collection import Collection
    +from minimongodb.oplog.entry import OplogEntry
    +
    +
    +def replay(
    +    entries: Iterable[OplogEntry],
    +    target: Collection | Mapping[str, Collection],
    +    *,
    +    after_sequence: int = 0,
    +) -> int:
    +    """Apply entries after a checkpoint sequence and return the last seen one."""
    +
    +    last_sequence = after_sequence
    +    for entry in entries:
    +        if entry.sequence <= after_sequence:
    +            continue
    +        collection = (
    +            target
    +            if isinstance(target, Collection)
    +            else target[entry.collection]
    +        )
    +        collection._apply_oplog_entry(entry)
    +        last_sequence = max(last_sequence, entry.sequence)
    +    return last_sequence
    ```

??? note "文件差异：src/minimongodb/plan/__init__.py"
    ```diff
    diff --git a/src/minimongodb/plan/__init__.py b/src/minimongodb/plan/__init__.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..b53988c97a7ffa4f36e494cf9453e82d7b29a5eb
    --- /dev/null
    +++ b/src/minimongodb/plan/__init__.py
    @@ -0,0 +1,7 @@
    +"""M2 placeholder for COLLSCAN/IXSCAN planning and ``explain``.
    +
    +M1 always scans the deterministic in-memory document list, except that the
    +private ``_id`` map enforces uniqueness and supports recovery identity lookup.
    +M2 will add plan nodes, selection estimates, secondary-index scans, and public
    +explain statistics.  No callable planner is exposed early.
    +"""
    ```

??? note "文件差异：src/minimongodb/update/operators.py"
    ```diff
    diff --git a/src/minimongodb/update/operators.py b/src/minimongodb/update/operators.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..96a573d9e95a021c26e01866ffa7d13168a70017
    --- /dev/null
    +++ b/src/minimongodb/update/operators.py
    @@ -0,0 +1,110 @@
    +"""Apply M1 update operators to an isolated document copy.
    +
    +Collection code clones a stored document first, invokes this module, validates
    +the result, and only then swaps it into storage.  That order is the miniature
    +version of atomic single-document updates: a failing second operator cannot
    +leave the first operator half-applied.
    +"""
    +
    +from __future__ import annotations
    +
    +from numbers import Real
    +from typing import Any
    +
    +from minimongodb.bson import (
    +    MISSING,
    +    bson_equal,
    +    clone_document,
    +    get_path,
    +    set_path,
    +    unset_path,
    +)
    +from minimongodb.errors import ImmutableIdError, InvalidUpdateError, PathError
    +from minimongodb.query import matches
    +
    +SUPPORTED_OPERATORS = {"$set", "$unset", "$inc", "$push", "$pull"}
    +
    +
    +def _guards_id(path: str) -> None:
    +    if path == "_id" or path.startswith("_id."):
    +        raise ImmutableIdError("_id is immutable")
    +
    +
    +def _mapping_operand(operator: str, operand: Any) -> dict[str, Any]:
    +    if not isinstance(operand, dict):
    +        raise InvalidUpdateError(f"{operator} requires a document operand")
    +    return operand
    +
    +
    +def apply_operator_update(
    +    original: dict[str, Any], update: dict[str, Any]
    +) -> dict[str, Any]:
    +    """Return an updated copy, never mutating the stored original."""
    +
    +    if not update or not all(key.startswith("$") for key in update):
    +        raise InvalidUpdateError("operator update must contain only $ operators")
    +    unknown = set(update) - SUPPORTED_OPERATORS
    +    if unknown:
    +        raise InvalidUpdateError(f"unsupported update operator: {sorted(unknown)[0]}")
    +
    +    document = clone_document(original)
    +    try:
    +        for operator, raw_operand in update.items():
    +            operand = _mapping_operand(operator, raw_operand)
    +            for path, value in operand.items():
    +                _guards_id(path)
    +                if operator == "$set":
    +                    set_path(document, path, value)
    +                elif operator == "$unset":
    +                    unset_path(document, path)
    +                elif operator == "$inc":
    +                    current = get_path(document, path)
    +                    if isinstance(value, bool) or not isinstance(value, Real):
    +                        raise InvalidUpdateError("$inc amount must be numeric")
    +                    if current is MISSING:
    +                        set_path(document, path, value)
    +                    elif isinstance(current, bool) or not isinstance(current, Real):
    +                        raise InvalidUpdateError("$inc target must be numeric")
    +                    else:
    +                        set_path(document, path, current + value)
    +                elif operator == "$push":
    +                    current = get_path(document, path)
    +                    if current is MISSING:
    +                        set_path(document, path, [value])
    +                    elif not isinstance(current, list):
    +                        raise InvalidUpdateError("$push target must be an array")
    +                    else:
    +                        current.append(value)
    +                elif operator == "$pull":
    +                    current = get_path(document, path)
    +                    if current is MISSING:
    +                        continue
    +                    if not isinstance(current, list):
    +                        raise InvalidUpdateError("$pull target must be an array")
    +                    current[:] = [
    +                        item for item in current if not matches({"value": item}, {"value": value})
    +                    ]
    +    except PathError as error:
    +        raise InvalidUpdateError(str(error)) from error
    +    # Values in the user's update document may themselves be mutable.  The
    +    # second boundary copy both validates those newly introduced values and
    +    # prevents later caller mutations from changing stored state.
    +    return clone_document(document)
    +
    +
    +def replacement_document(
    +    original: dict[str, Any], replacement: dict[str, Any]
    +) -> dict[str, Any]:
    +    """Build a replacement while preserving an omitted immutable ``_id``."""
    +
    +    if not isinstance(replacement, dict):
    +        raise InvalidUpdateError("replacement must be a document")
    +    if any(key.startswith("$") for key in replacement):
    +        raise InvalidUpdateError("replacement cannot contain top-level operators")
    +    result = clone_document(replacement)
    +    old_id = original["_id"]
    +    if "_id" in result and not bson_equal(result["_id"], old_id):
    +        raise ImmutableIdError("_id is immutable")
    +    if "_id" not in result:
    +        result["_id"] = old_id
    +    return result
    ```

**是什么，为什么现在需要**

Collection 拥有活文档与索引；Database 拥有命名集合与持久性。算子更新在写日志前变成最终状态后镜像。

**在运行时做什么**

写入先校验候选状态、分配序号、记录持久转换，再发布受控状态。启动时载入 Checkpoint，只回放更新的 Entry。

**关键语句理解**

记录最终赋值而非用户命令，使回放幂等，并避免重复恢复把 `$inc` 执行两次。

#### 包、Fixture 与工程支撑

保持包导出、测试语料、依赖与运行环境可复现。

??? note "支撑文件差异（3 个文件）"
    **`src/minimongodb/__init__.py`**

    ```diff
    diff --git a/src/minimongodb/__init__.py b/src/minimongodb/__init__.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..ff5d17162ae14edb0fc008c6f211391e3851d339
    --- /dev/null
    +++ b/src/minimongodb/__init__.py
    @@ -0,0 +1,31 @@
    +"""MiniMongoDB public API.
    +
    +The package exposes the small surface a learner needs for labs.  Internal
    +packages remain importable for focused tests, but applications should start
    +with :class:`Collection` or :class:`Database`.
    +"""
    +
    +from minimongodb.bson import CounterObjectIdGenerator, ObjectId
    +from minimongodb.collection import (
    +    Collection,
    +    DeleteResult,
    +    InsertManyResult,
    +    InsertOneResult,
    +    UpdateResult,
    +)
    +from minimongodb.database import Database
    +from minimongodb.oplog import Oplog, OplogEntry, replay
    +
    +__all__ = [
    +    "Collection",
    +    "CounterObjectIdGenerator",
    +    "Database",
    +    "DeleteResult",
    +    "InsertManyResult",
    +    "InsertOneResult",
    +    "ObjectId",
    +    "Oplog",
    +    "OplogEntry",
    +    "UpdateResult",
    +    "replay",
    +]
    ```

    **`src/minimongodb/index/__init__.py`**

    ```diff
    diff --git a/src/minimongodb/index/__init__.py b/src/minimongodb/index/__init__.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..33e63b12571722e877bb78200e64c27ae7776e30
    --- /dev/null
    +++ b/src/minimongodb/index/__init__.py
    @@ -0,0 +1,5 @@
    +"""Index boundaries; M1 implements only the mandatory unique ``_id`` index."""
    +
    +from minimongodb.index.id_index import IdIndex
    +
    +__all__ = ["IdIndex"]
    ```

    **`src/minimongodb/update/__init__.py`**

    ```diff
    diff --git a/src/minimongodb/update/__init__.py b/src/minimongodb/update/__init__.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..271acc4566bd053fc6aec72ebc71d618877911dc
    --- /dev/null
    +++ b/src/minimongodb/update/__init__.py
    @@ -0,0 +1,5 @@
    +"""Document replacement and Mongo-shaped update operators."""
    +
    +from minimongodb.update.operators import apply_operator_update, replacement_document
    +
    +__all__ = ["apply_operator_update", "replacement_document"]
    ```


### 验证证据

运行 `uv run pytest -q $(cat journey/stages/04-crud-update-recovery/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

记录最终赋值而非用户命令，使回放幂等，并避免重复恢复把 `$inc` 执行两次。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 6 章](https://github.com/system-in-miniature/mini-mongodb/blob/main/docs/zh/tutorial/06-oplog.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-mongodb/blob/main/journey/stages/04-crud-update-recovery/stage.patch)
