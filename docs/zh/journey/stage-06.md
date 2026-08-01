# Stage 06 · 索引计划与聚合管道

### 目标

实现索引计划与聚合管道，并能从可执行反例、运行时状态与关键语句解释其边界。

??? note "交付文件"
    - `src/minimongodb/aggregate/__init__.py`
    - `src/minimongodb/collection.py`
    - `src/minimongodb/database.py`
    - `src/minimongodb/errors.py`
    - `src/minimongodb/index/__init__.py`
    - `src/minimongodb/index/id_index.py`
    - `src/minimongodb/index/secondary.py`
    - `src/minimongodb/plan/__init__.py`
    - `src/minimongodb/storage/recovery.py`
    - `tests/test_aggregate.py`
    - `tests/test_indexes.py`
    - `tests/test_planner.py`

### 当前遇到的问题

M2 Collection 需要可复用访问路径与分阶段文档变换，但两者都必须保持与 Collection Scan 相同的 BSON 与所有权语义。

### 测试契约

#### 先看会坏在哪里

测试组合 Multikey 与 Compound Index、选择度与 Explain 计数，以及 Match、Project、Group、BSON 感知 Sort、Limit 和错误 Pipeline Stage。

??? note "文件差异：tests/test_aggregate.py"
    ```diff
    diff --git a/tests/test_aggregate.py b/tests/test_aggregate.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..75fd4de222830a4e65fb694a5c2e6d79ca26cf5b
    --- /dev/null
    +++ b/tests/test_aggregate.py
    @@ -0,0 +1,111 @@
    +"""Aggregation stages compose as a deterministic document operator pipeline."""
    +
    +import pytest
    +
    +from minimongodb import Collection
    +from minimongodb.errors import InvalidPipelineError
    +
    +
    +def test_match_project_sort_and_limit_pipeline() -> None:
    +    collection = Collection("sales")
    +    collection.insert_many(
    +        [
    +            {"_id": 1, "region": "west", "item": {"name": "pen"}, "amount": 3},
    +            {"_id": 2, "region": "east", "item": {"name": "book"}, "amount": 9},
    +            {"_id": 3, "region": "west", "item": {"name": "book"}, "amount": 7},
    +        ]
    +    )
    +
    +    assert collection.aggregate(
    +        [
    +            {"$match": {"region": "west"}},
    +            {"$project": {"_id": 0, "name": "$item.name", "amount": 1}},
    +            {"$sort": {"amount": -1}},
    +            {"$limit": 1},
    +        ]
    +    ) == [{"name": "book", "amount": 7}]
    +
    +
    +def test_group_supports_all_minimum_accumulators() -> None:
    +    collection = Collection("sales")
    +    collection.insert_many(
    +        [
    +            {"_id": 1, "region": "west", "amount": 3},
    +            {"_id": 2, "region": "east", "amount": 9},
    +            {"_id": 3, "region": "west", "amount": 7},
    +        ]
    +    )
    +
    +    assert collection.aggregate(
    +        [
    +            {
    +                "$group": {
    +                    "_id": "$region",
    +                    "count": {"$sum": 1},
    +                    "total": {"$sum": "$amount"},
    +                    "average": {"$avg": "$amount"},
    +                    "minimum": {"$min": "$amount"},
    +                    "maximum": {"$max": "$amount"},
    +                    "amounts": {"$push": "$amount"},
    +                }
    +            },
    +            {"$sort": {"_id": 1}},
    +        ]
    +    ) == [
    +        {
    +            "_id": "east",
    +            "count": 1,
    +            "total": 9,
    +            "average": 9.0,
    +            "minimum": 9,
    +            "maximum": 9,
    +            "amounts": [9],
    +        },
    +        {
    +            "_id": "west",
    +            "count": 2,
    +            "total": 10,
    +            "average": 5.0,
    +            "minimum": 3,
    +            "maximum": 7,
    +            "amounts": [3, 7],
    +        },
    +    ]
    +
    +
    +def test_group_min_keeps_null_as_a_real_bson_value() -> None:
    +    collection = Collection("values")
    +    collection.insert_many([{"_id": 1, "x": None}, {"_id": 2, "x": 3}])
    +    assert collection.aggregate(
    +        [
    +            {
    +                "$group": {
    +                    "_id": None,
    +                    "minimum": {"$min": "$x"},
    +                    "maximum": {"$max": "$x"},
    +                }
    +            }
    +        ]
    +    ) == [{"_id": None, "minimum": None, "maximum": 3}]
    +
    +
    +def test_project_nested_expression_does_not_leak_missing_sentinel() -> None:
    +    collection = Collection("values")
    +    collection.insert_one({"_id": 1})
    +    assert collection.aggregate(
    +        [{"$project": {"_id": 0, "object": {"value": "$missing"}}}]
    +    ) == [{"object": {}}]
    +
    +
    +@pytest.mark.parametrize(
    +    "pipeline",
    +    [
    +        [{"$unknown": {}}],
    +        [{"$match": {}, "$limit": 1}],
    +        [{"$limit": -1}],
    +        [{"$group": {"_id": "$x", "bad": {"$median": "$x"}}}],
    +    ],
    +)
    +def test_invalid_pipeline_stages_are_rejected(pipeline: list[dict]) -> None:
    +    with pytest.raises(InvalidPipelineError):
    +        Collection().aggregate(pipeline)
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

测试组合 Multikey 与 Compound Index、选择度与 Explain 计数，以及 Match、Project、Group、BSON 感知 Sort、Limit 和错误 Pipeline Stage。

**关键测试语句**

```python
assert entry.payload is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/test_indexes.py"
    ```diff
    diff --git a/tests/test_indexes.py b/tests/test_indexes.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..5a2a7637eefdf0039965adfb6e6eebc4a9081d30
    --- /dev/null
    +++ b/tests/test_indexes.py
    @@ -0,0 +1,161 @@
    +"""Secondary indexes preserve BSON identity and expand multikey documents."""
    +
    +from pathlib import Path
    +
    +import pytest
    +
    +from minimongodb import Collection, Database
    +from minimongodb.errors import DuplicateKeyError
    +from minimongodb.oplog import Oplog
    +
    +
    +def test_single_and_compound_indexes_accept_dotted_paths() -> None:
    +    collection = Collection("people")
    +    collection.insert_many(
    +        [
    +            {"_id": 1, "team": "db", "profile": {"city": "Paris"}},
    +            {"_id": 2, "team": "db", "profile": {"city": "Oslo"}},
    +            {"_id": 3, "team": "web", "profile": {"city": "Paris"}},
    +        ]
    +    )
    +
    +    assert collection.create_index("profile.city") == "profile.city_1"
    +    assert (
    +        collection.create_index([("team", 1), ("profile.city", 1)])
    +        == "team_1_profile.city_1"
    +    )
    +    assert collection.find({"team": "db", "profile.city": "Oslo"}) == [
    +        {"_id": 2, "team": "db", "profile": {"city": "Oslo"}}
    +    ]
    +
    +
    +def test_multikey_index_emits_multiple_deduplicated_keys_per_document() -> None:
    +    collection = Collection("articles")
    +    collection.insert_many(
    +        [
    +            {"_id": 1, "tags": ["database", "python", "database"]},
    +            {"_id": 2, "tags": ["storage"]},
    +            {"_id": 3, "tags": ["database"]},
    +        ]
    +    )
    +    collection.create_index("tags")
    +
    +    explanation = collection.explain({"tags": "database"})
    +    assert explanation["queryPlanner"]["winningPlan"]["stage"] == "IXSCAN"
    +    assert explanation["executionStats"] == {
    +        "nReturned": 2,
    +        "keysExamined": 1,
    +        "docsExamined": 2,
    +    }
    +    assert [document["_id"] for document in collection.find({"tags": "database"})] == [
    +        1,
    +        3,
    +    ]
    +
    +
    +def test_multikey_metadata_tracks_array_expansion_not_distinct_key_count() -> None:
    +    collection = Collection("articles")
    +    collection.insert_one({"_id": 1, "tags": ["same", "same"]})
    +    collection.create_index("tags")
    +    assert collection.index_information()["tags_1"]["multikey"] is True
    +    assert collection.index_information()["tags_1"]["entries"] == 1
    +
    +
    +def test_unique_index_uses_canonical_bson_keys_and_multikey_ownership() -> None:
    +    collection = Collection("users")
    +    collection.create_index("handle", unique=True)
    +    collection.insert_many([{"_id": 1, "handle": True}, {"_id": 2, "handle": 1}])
    +    with pytest.raises(
    +        DuplicateKeyError, match=r"duplicate key for index handle_1"
    +    ):
    +        collection.insert_one({"_id": 3, "handle": 1.0})
    +
    +    tags = Collection("tags")
    +    tags.create_index("values", unique=True)
    +    tags.insert_one({"_id": 1, "values": ["same", "same"]})
    +    with pytest.raises(
    +        DuplicateKeyError, match=r"duplicate key for index values_1"
    +    ):
    +        tags.insert_one({"_id": 2, "values": ["same"]})
    +
    +
    +def test_unique_index_validates_existing_documents_and_whole_insert_batch() -> None:
    +    collection = Collection("users")
    +    collection.insert_many(
    +        [{"_id": 1, "email": "same"}, {"_id": 2, "email": "same"}]
    +    )
    +    with pytest.raises(DuplicateKeyError):
    +        collection.create_index("email", unique=True)
    +
    +    clean = Collection("users")
    +    clean.create_index("email", unique=True)
    +    with pytest.raises(DuplicateKeyError):
    +        clean.insert_many(
    +            [{"_id": 1, "email": "same"}, {"_id": 2, "email": "same"}]
    +        )
    +    assert clean.find() == []
    +
    +
    +def test_updates_and_deletes_maintain_unique_secondary_indexes() -> None:
    +    collection = Collection("users")
    +    collection.create_index("email", unique=True)
    +    collection.insert_many(
    +        [{"_id": 1, "email": "one"}, {"_id": 2, "email": "two"}]
    +    )
    +
    +    with pytest.raises(DuplicateKeyError):
    +        collection.update_one({"_id": 1}, {"$set": {"email": "two"}})
    +    assert collection.find_one({"_id": 1})["email"] == "one"
    +
    +    collection.delete_one({"_id": 2})
    +    collection.update_one({"_id": 1}, {"$set": {"email": "two"}})
    +    assert collection.find({"email": "two"}) == [{"_id": 1, "email": "two"}]
    +
    +
    +def test_secondary_index_is_not_published_when_journal_append_fails() -> None:
    +    state = {"fail": False}
    +
    +    def listener(entry) -> None:
    +        if state["fail"]:
    +            raise OSError("injected journal failure")
    +
    +    collection = Collection("items", oplog=Oplog(listener=listener))
    +    collection.create_index("kind")
    +    collection.insert_one({"_id": 1, "kind": "visible"})
    +    state["fail"] = True
    +
    +    with pytest.raises(OSError, match="injected journal failure"):
    +        collection.insert_one({"_id": 2, "kind": "hidden"})
    +
    +    assert collection.find({"kind": "hidden"}) == []
    +    assert collection.explain({"kind": "hidden"})["executionStats"]["nReturned"] == 0
    +
    +
    +@pytest.mark.parametrize("checkpointed", [False, True])
    +def test_index_definition_survives_journal_and_checkpoint_recovery(
    +    tmp_path: Path, checkpointed: bool
    +) -> None:
    +    database = Database(tmp_path)
    +    articles = database["articles"]
    +    articles.create_index("tags", unique=True)
    +    articles.insert_many(
    +        [
    +            {"_id": 1, "tags": ["database", "storage"]},
    +            {"_id": 2, "tags": ["python"]},
    +        ]
    +    )
    +    if checkpointed:
    +        database.checkpoint()
    +
    +    recovered = Database(tmp_path)["articles"]
    +    assert recovered.index_information()["tags_1"] == {
    +        "key": {"tags": 1},
    +        "unique": True,
    +        "multikey": True,
    +        "entries": 3,
    +    }
    +    assert recovered.explain({"tags": "database"})["queryPlanner"]["winningPlan"][
    +        "stage"
    +    ] == "IXSCAN"
    +    with pytest.raises(DuplicateKeyError):
    +        recovered.insert_one({"_id": 3, "tags": ["database"]})
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

测试组合 Multikey 与 Compound Index、选择度与 Explain 计数，以及 Match、Project、Group、BSON 感知 Sort、Limit 和错误 Pipeline Stage。

**关键测试语句**

```python
assert entry.payload is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/test_planner.py"
    ```diff
    diff --git a/tests/test_planner.py b/tests/test_planner.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..fd9cb1e442201cf5b86a0d925f486bf627632673
    --- /dev/null
    +++ b/tests/test_planner.py
    @@ -0,0 +1,120 @@
    +"""Planner selection is deterministic and explain uses MongoDB terminology."""
    +
    +from minimongodb import Collection
    +
    +
    +def _collection() -> Collection:
    +    collection = Collection("events")
    +    collection.insert_many(
    +        [
    +            {"_id": 1, "tenant": "a", "kind": "rare"},
    +            {"_id": 2, "tenant": "a", "kind": "common"},
    +            {"_id": 3, "tenant": "b", "kind": "common"},
    +            {"_id": 4, "tenant": "b", "kind": "common"},
    +        ]
    +    )
    +    return collection
    +
    +
    +def test_explain_changes_from_collscan_to_selective_ixscan() -> None:
    +    collection = _collection()
    +
    +    before = collection.explain({"kind": "rare"})
    +    assert before["queryPlanner"]["winningPlan"] == {"stage": "COLLSCAN"}
    +    assert before["executionStats"] == {
    +        "nReturned": 1,
    +        "keysExamined": 0,
    +        "docsExamined": 4,
    +    }
    +
    +    collection.create_index("kind")
    +    after = collection.explain({"kind": "rare"})
    +    assert after["queryPlanner"]["winningPlan"] == {
    +        "stage": "IXSCAN",
    +        "indexName": "kind_1",
    +        "keyPattern": {"kind": 1},
    +        "indexBounds": {"kind": "rare"},
    +    }
    +    assert after["executionStats"] == {
    +        "nReturned": 1,
    +        "keysExamined": 1,
    +        "docsExamined": 1,
    +    }
    +
    +
    +def test_compound_index_requires_a_leftmost_prefix() -> None:
    +    collection = _collection()
    +    collection.create_index([("tenant", 1), ("kind", 1)])
    +
    +    prefix = collection.explain({"tenant": "a", "kind": "rare"})
    +    assert prefix["queryPlanner"]["winningPlan"]["stage"] == "IXSCAN"
    +    assert prefix["queryPlanner"]["winningPlan"]["indexName"] == "tenant_1_kind_1"
    +
    +    no_prefix = collection.explain({"kind": "rare"})
    +    assert no_prefix["queryPlanner"]["winningPlan"] == {"stage": "COLLSCAN"}
    +
    +
    +def test_unselective_index_loses_to_collection_scan() -> None:
    +    collection = _collection()
    +    collection.create_index("kind")
    +    explanation = collection.explain({"kind": {"$in": ["rare", "common"]}})
    +    assert explanation["queryPlanner"]["winningPlan"] == {"stage": "COLLSCAN"}
    +
    +
    +def test_automatic_id_index_serves_identity_equality() -> None:
    +    collection = _collection()
    +    explanation = collection.explain({"_id": 3})
    +    assert explanation["queryPlanner"]["winningPlan"] == {
    +        "stage": "IXSCAN",
    +        "indexName": "_id_",
    +        "keyPattern": {"_id": 1},
    +        "indexBounds": {"_id": 3},
    +    }
    +    assert explanation["executionStats"] == {
    +        "nReturned": 1,
    +        "keysExamined": 1,
    +        "docsExamined": 1,
    +    }
    +
    +
    +def test_id_index_falls_back_for_scalar_matching_inside_array_ids() -> None:
    +    collection = Collection("array_ids")
    +    collection.insert_many([{"_id": [1, 2], "value": "array"}, {"_id": 3}])
    +
    +    assert collection.find({"_id": 1}) == [
    +        {"_id": [1, 2], "value": "array"}
    +    ]
    +    assert collection.find({"_id": {"$eq": 2}}) == [
    +        {"_id": [1, 2], "value": "array"}
    +    ]
    +    assert collection.find({"_id": {"$in": [1]}}) == [
    +        {"_id": [1, 2], "value": "array"}
    +    ]
    +    assert collection.explain({"_id": 1})["queryPlanner"]["winningPlan"] == {
    +        "stage": "COLLSCAN"
    +    }
    +    assert collection.explain({"_id": [1, 2]})["queryPlanner"]["winningPlan"][
    +        "indexName"
    +    ] == "_id_"
    +
    +
    +def test_multikey_planner_falls_back_when_leaf_bounds_cannot_preserve_matching() -> None:
    +    collection = Collection("arrays")
    +    collection.insert_many(
    +        [{"_id": 1, "values": [1, 20]}, {"_id": 2, "values": [3, 4]}]
    +    )
    +    literal_query = {"values": [1, 20]}
    +    cross_element_query = {"values": {"$gt": 10, "$lt": 5}}
    +    expected_literal = collection.find(literal_query)
    +    expected_cross_element = collection.find(cross_element_query)
    +
    +    collection.create_index("values")
    +
    +    assert collection.find(literal_query) == expected_literal
    +    assert collection.find(cross_element_query) == expected_cross_element
    +    assert collection.explain(literal_query)["queryPlanner"]["winningPlan"] == {
    +        "stage": "COLLSCAN"
    +    }
    +    assert collection.explain(cross_element_query)["queryPlanner"][
    +        "winningPlan"
    +    ] == {"stage": "COLLSCAN"}
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

测试组合 Multikey 与 Compound Index、选择度与 Explain 计数，以及 Match、Project、Group、BSON 感知 Sort、Limit 和错误 Pipeline Stage。

**关键测试语句**

```python
assert entry.payload is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

索引把 Canonical Key 映射到 Candidate，Plan 显式选择 COLLSCAN 或 IXSCAN，Aggregation Pipeline 则组合有序的流式或阻塞文档算子。

### 为什么需要这个机制

M2 Collection 需要可复用访问路径与分阶段文档变换，但两者都必须保持与 Collection Scan 相同的 BSON 与所有权语义。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

写入在发布前暂存全部索引项；读取取回并重检计划候选；随后聚合把受控文档依次传过每个已校验 Stage。

### 机制板块

#### 索引计划与聚合管道机制

写入在发布前暂存全部索引项；读取取回并重检计划候选；随后聚合把受控文档依次传过每个已校验 Stage。

??? note "文件差异：src/minimongodb/aggregate/__init__.py"
    ```diff
    diff --git a/src/minimongodb/aggregate/__init__.py b/src/minimongodb/aggregate/__init__.py
    index a346aa409dfc011c4fcd58cc17d7b2b02882b265..901bdaad1a6250c8effa256ffec7fff30102f3f7 100644
    --- a/src/minimongodb/aggregate/__init__.py
    +++ b/src/minimongodb/aggregate/__init__.py
    @@ -1,7 +1,240 @@
    -"""M2 placeholder for ``$match/$project/$group/$sort/$limit`` pipelines.
    +"""Aggregation as a sequence of small document-to-document operators.

    -The future package will model aggregation stages as a pull-based operator
    -stream so it can be compared directly with MiniPostgres' relational execution
    -operators.  M1 does not accept aggregation syntax or pretend a list
    -comprehension is a complete pipeline.
    +Each stage consumes the previous stage's iterable.  Streaming stages
    +(``$match``, ``$project``, ``$limit``) stay lazy; blocking stages
    +(``$group``, ``$sort``) materialize exactly where their semantics require it.
    +That boundary is the document-model counterpart to relational operator trees.
     """
    +
    +from __future__ import annotations
    +
    +from copy import deepcopy
    +from functools import cmp_to_key
    +from typing import Any, Iterable, Iterator
    +
    +from minimongodb.bson import (
    +    MISSING,
    +    bson_compare,
    +    canonical_key,
    +    clone_document,
    +    get_path,
    +    set_path,
    +    unset_path,
    +)
    +from minimongodb.errors import InvalidPipelineError
    +from minimongodb.query import matches
    +
    +_UNSET = object()
    +
    +
    +def execute_pipeline(
    +    documents: Iterable[dict[str, Any]], pipeline: list[dict[str, Any]]
    +) -> list[dict[str, Any]]:
    +    if not isinstance(pipeline, list):
    +        raise InvalidPipelineError("pipeline must be an array of stages")
    +    stream: Iterable[dict[str, Any]] = (
    +        clone_document(document) for document in documents
    +    )
    +    for stage in pipeline:
    +        if not isinstance(stage, dict) or len(stage) != 1:
    +            raise InvalidPipelineError("each stage must contain exactly one operator")
    +        operator, specification = next(iter(stage.items()))
    +        if operator == "$match":
    +            if not isinstance(specification, dict):
    +                raise InvalidPipelineError("$match requires a query document")
    +            stream = _match(stream, specification)
    +        elif operator == "$project":
    +            stream = _project(stream, specification)
    +        elif operator == "$group":
    +            stream = _group(stream, specification)
    +        elif operator == "$sort":
    +            stream = _sort(stream, specification)
    +        elif operator == "$limit":
    +            stream = _limit(stream, specification)
    +        else:
    +            raise InvalidPipelineError(f"unsupported pipeline stage: {operator}")
    +    return list(stream)
    +
    +
    +def _match(
    +    documents: Iterable[dict[str, Any]], query: dict[str, Any]
    +) -> Iterator[dict[str, Any]]:
    +    for document in documents:
    +        if matches(document, query):
    +            yield document
    +
    +
    +def _project(
    +    documents: Iterable[dict[str, Any]], specification: Any
    +) -> Iterator[dict[str, Any]]:
    +    if not isinstance(specification, dict) or not specification:
    +        raise InvalidPipelineError("$project requires a non-empty document")
    +    excluded = {
    +        field for field, expression in specification.items() if expression in (0, False)
    +    }
    +    included = set(specification) - excluded
    +    if excluded - {"_id"} and included:
    +        raise InvalidPipelineError(
    +            "$project cannot mix exclusion with inclusion or computed fields"
    +        )
    +
    +    for document in documents:
    +        if included:
    +            projected: dict[str, Any] = {}
    +            if specification.get("_id", 1) not in (0, False) and "_id" in document:
    +                projected["_id"] = deepcopy(document["_id"])
    +            for field in included - {"_id"}:
    +                expression = specification[field]
    +                value = (
    +                    get_path(document, field)
    +                    if expression in (1, True)
    +                    else _evaluate(document, expression)
    +                )
    +                if value is not MISSING:
    +                    set_path(projected, field, deepcopy(value))
    +            yield projected
    +        else:
    +            projected = clone_document(document)
    +            for field in excluded:
    +                unset_path(projected, field)
    +            yield projected
    +
    +
    +def _group(
    +    documents: Iterable[dict[str, Any]], specification: Any
    +) -> Iterable[dict[str, Any]]:
    +    if not isinstance(specification, dict) or "_id" not in specification:
    +        raise InvalidPipelineError("$group requires an _id expression")
    +    accumulator_specs: dict[str, tuple[str, Any]] = {}
    +    for output, accumulator in specification.items():
    +        if output == "_id":
    +            continue
    +        if not isinstance(accumulator, dict) or len(accumulator) != 1:
    +            raise InvalidPipelineError("group fields require one accumulator")
    +        operator, expression = next(iter(accumulator.items()))
    +        if operator not in {"$sum", "$avg", "$min", "$max", "$push"}:
    +            raise InvalidPipelineError(f"unsupported group accumulator: {operator}")
    +        accumulator_specs[output] = (operator, expression)
    +
    +    groups: dict[tuple[Any, ...], dict[str, Any]] = {}
    +    averages: dict[tuple[Any, ...], dict[str, tuple[float, int]]] = {}
    +    for document in documents:
    +        group_value = _evaluate(document, specification["_id"])
    +        if group_value is MISSING:
    +            group_value = None
    +        group_key = canonical_key(group_value)
    +        if group_key not in groups:
    +            groups[group_key] = {"_id": deepcopy(group_value)}
    +            averages[group_key] = {}
    +            for output, (operator, _expression) in accumulator_specs.items():
    +                if operator == "$push":
    +                    groups[group_key][output] = []
    +                elif operator in {"$min", "$max"}:
    +                    groups[group_key][output] = _UNSET
    +                else:
    +                    groups[group_key][output] = None
    +
    +        result = groups[group_key]
    +        for output, (operator, expression) in accumulator_specs.items():
    +            value = _evaluate(document, expression)
    +            if operator == "$push":
    +                result[output].append(None if value is MISSING else deepcopy(value))
    +            elif operator == "$sum":
    +                numeric = _numeric(value)
    +                result[output] = (result[output] or 0) + (numeric or 0)
    +            elif operator == "$avg":
    +                numeric = _numeric(value)
    +                if numeric is not None:
    +                    total, count = averages[group_key].get(output, (0.0, 0))
    +                    averages[group_key][output] = (total + numeric, count + 1)
    +            elif value is not MISSING:
    +                current = result[output]
    +                if current is _UNSET:
    +                    result[output] = deepcopy(value)
    +                else:
    +                    compared = bson_compare(value, current)
    +                    if (operator == "$min" and compared < 0) or (
    +                        operator == "$max" and compared > 0
    +                    ):
    +                        result[output] = deepcopy(value)
    +
    +    for group_key, result in groups.items():
    +        for output, (operator, _expression) in accumulator_specs.items():
    +            if operator == "$avg":
    +                aggregate = averages[group_key].get(output)
    +                result[output] = (
    +                    aggregate[0] / aggregate[1] if aggregate is not None else None
    +                )
    +            elif operator == "$sum" and result[output] is None:
    +                result[output] = 0
    +            elif operator in {"$min", "$max"} and result[output] is _UNSET:
    +                result[output] = None
    +    return groups.values()
    +
    +
    +def _sort(
    +    documents: Iterable[dict[str, Any]], specification: Any
    +) -> Iterable[dict[str, Any]]:
    +    if not isinstance(specification, dict) or not specification:
    +        raise InvalidPipelineError("$sort requires a non-empty key pattern")
    +    if any(direction not in (1, -1) for direction in specification.values()):
    +        raise InvalidPipelineError("$sort directions must be 1 or -1")
    +
    +    def compare(left: dict[str, Any], right: dict[str, Any]) -> int:
    +        for field, direction in specification.items():
    +            left_value = get_path(left, field)
    +            right_value = get_path(right, field)
    +            if left_value is MISSING:
    +                left_value = None
    +            if right_value is MISSING:
    +                right_value = None
    +            compared = bson_compare(left_value, right_value)
    +            if compared:
    +                return compared * direction
    +        return 0
    +
    +    return sorted(documents, key=cmp_to_key(compare))
    +
    +
    +def _limit(
    +    documents: Iterable[dict[str, Any]], specification: Any
    +) -> Iterator[dict[str, Any]]:
    +    if (
    +        isinstance(specification, bool)
    +        or not isinstance(specification, int)
    +        or specification < 0
    +    ):
    +        raise InvalidPipelineError("$limit requires a non-negative integer")
    +    for position, document in enumerate(documents):
    +        if position >= specification:
    +            break
    +        yield document
    +
    +
    +def _evaluate(document: dict[str, Any], expression: Any) -> Any:
    +    if isinstance(expression, str) and expression.startswith("$"):
    +        if expression == "$":
    +            return document
    +        return get_path(document, expression[1:])
    +    if isinstance(expression, dict):
    +        evaluated: dict[str, Any] = {}
    +        for key, child in expression.items():
    +            value = _evaluate(document, child)
    +            if value is not MISSING:
    +                evaluated[key] = value
    +        return evaluated
    +    if isinstance(expression, list):
    +        return [
    +            None if (value := _evaluate(document, child)) is MISSING else value
    +            for child in expression
    +        ]
    +    return deepcopy(expression)
    +
    +
    +def _numeric(value: Any) -> int | float | None:
    +    if isinstance(value, bool) or not isinstance(value, (int, float)):
    +        return None
    +    return value
    +
    +
    +__all__ = ["execute_pipeline"]
    ```

??? note "文件差异：src/minimongodb/collection.py"
    ```diff
    diff --git a/src/minimongodb/collection.py b/src/minimongodb/collection.py
    index 7907fb82546093b8612abaa1db4a4ea69eab9b91..0292528dd6fa73dd6b6ce264f19c1023be7d5ae0 100644
    --- a/src/minimongodb/collection.py
    +++ b/src/minimongodb/collection.py
    @@ -1,8 +1,9 @@
    -"""Collection is the M1 convergence layer for matching, mutation, and indexing.
    +"""Collection converges matching, durable mutation, indexing, and execution.

     Documents are kept in insertion order for deterministic teaching output.  The
    -separate ``IdIndex`` supplies uniqueness and direct identity lookup; M2 will
    -add secondary indexes and planning without changing this public CRUD surface.
    +identity and secondary indexes publish only after the oplog listener has made
    +the post-image durable. Query planning never changes result order or matching
    +semantics; it only narrows which stored documents the matcher must examine.
     """

     from __future__ import annotations
    @@ -10,6 +11,7 @@ from __future__ import annotations
     from dataclasses import dataclass
     from typing import Any, Callable, Iterable

    +from minimongodb.aggregate import execute_pipeline
     from minimongodb.bson import (
         CounterObjectIdGenerator,
         bson_equal,
    @@ -17,8 +19,14 @@ from minimongodb.bson import (
         clone_document,
     )
     from minimongodb.errors import DuplicateKeyError, InvalidUpdateError
    -from minimongodb.index import IdIndex
    +from minimongodb.index import (
    +    IdIndex,
    +    SecondaryIndex,
    +    default_index_name,
    +    normalize_index_spec,
    +)
     from minimongodb.oplog.entry import Oplog, OplogEntry
    +from minimongodb.plan import Plan, choose_plan
     from minimongodb.query import matches
     from minimongodb.update import apply_operator_update, replacement_document

    @@ -58,8 +66,99 @@ class Collection:
             self._id_generator = id_generator or CounterObjectIdGenerator()
             self._documents: list[dict[str, Any]] = []
             self._id_index = IdIndex()
    +        self._indexes: dict[str, SecondaryIndex] = {}
             self.oplog = oplog if oplog is not None else Oplog()

    +    def create_index(
    +        self,
    +        keys: str | dict[str, int] | Iterable[tuple[str, int]],
    +        *,
    +        unique: bool = False,
    +        name: str | None = None,
    +    ) -> str:
    +        """Build an index from the current snapshot before publishing its name."""
    +
    +        spec = normalize_index_spec(keys)
    +        index_name = name or default_index_name(spec)
    +        existing = self._indexes.get(index_name)
    +        if existing is not None:
    +            if existing.spec != spec or existing.unique != unique:
    +                raise ValueError(f"index name already has a different definition: {index_name}")
    +            return index_name
    +        index = SecondaryIndex(spec, name=index_name, unique=unique)
    +        index.validate_documents(self._documents)
    +        for document in self._documents:
    +            index.add(document)
    +        self.oplog.emit(
    +            self.name,
    +            "create_index",
    +            index_name,
    +            {
    +                "keys": [
    +                    {"field": field, "direction": direction}
    +                    for field, direction in spec
    +                ],
    +                "unique": unique,
    +                "name": index_name,
    +            },
    +        )
    +        self._indexes[index_name] = index
    +        return index_name
    +
    +    def index_information(self) -> dict[str, dict[str, Any]]:
    +        """Expose stable teaching metadata without leaking index internals."""
    +
    +        information: dict[str, dict[str, Any]] = {
    +            "_id_": {
    +                "key": {"_id": 1},
    +                "unique": True,
    +                "multikey": False,
    +                "entries": len(self._documents),
    +            }
    +        }
    +        information.update(
    +            {
    +                name: {
    +                    "key": index.key_pattern,
    +                    "unique": index.unique,
    +                    "multikey": index.is_multikey,
    +                    "entries": index.entry_count,
    +                }
    +                for name, index in self._indexes.items()
    +            }
    +        )
    +        return information
    +
    +    def _index_definitions(self) -> list[dict[str, Any]]:
    +        """Return checkpoint-safe definitions; entries rebuild from documents."""
    +
    +        return [
    +            {
    +                "keys": [
    +                    {"field": field, "direction": direction}
    +                    for field, direction in index.spec
    +                ],
    +                "unique": index.unique,
    +                "name": index.name,
    +            }
    +            for index in self._indexes.values()
    +        ]
    +
    +    def _restore_index(self, definition: dict[str, Any]) -> None:
    +        pairs = [
    +            (item["field"], item["direction"]) for item in definition["keys"]
    +        ]
    +        spec = normalize_index_spec(pairs)
    +        name = definition["name"]
    +        existing = self._indexes.get(name)
    +        if existing is not None:
    +            return
    +        index = SecondaryIndex(spec, name=name, unique=definition["unique"])
    +        index.validate_documents(self._documents)
    +        for document in self._documents:
    +            index.add(document)
    +        self._indexes[name] = index
    +
         def insert_one(self, document: dict[str, Any]) -> InsertOneResult:
             return InsertOneResult(self.insert_many([document]).inserted_ids[0])

    @@ -78,6 +177,9 @@ class Collection:
                     raise DuplicateKeyError(f"duplicate key for _id index: {key!r}")
                 candidates.append(candidate)

    +        for index in self._indexes.values():
    +            index.validate_documents(candidates)
    +
             # Validate the whole batch, then durably publish one document at a time.
             for candidate in candidates:
                 self.oplog.emit(
    @@ -85,23 +187,40 @@ class Collection:
                 )
                 self._documents.append(candidate)
                 self._id_index.add(candidate)
    +            for index in self._indexes.values():
    +                index.add(candidate)
             return InsertManyResult([candidate["_id"] for candidate in candidates])

         def find(self, query: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    -        return [
    -            clone_document(document)
    -            for document in self._documents
    -            if matches(document, query)
    -        ]
    +        documents, _plan, _keys_examined, _docs_examined = self._run_query(query)
    +        return [clone_document(document) for document in documents]

         def find_one(self, query: dict[str, Any] | None = None) -> dict[str, Any] | None:
    -        for document in self._documents:
    -            if matches(document, query):
    -                return clone_document(document)
    -        return None
    +        documents, _plan, _keys_examined, _docs_examined = self._run_query(query)
    +        return clone_document(documents[0]) if documents else None

         def count_documents(self, query: dict[str, Any] | None = None) -> int:
    -        return sum(matches(document, query) for document in self._documents)
    +        documents, _plan, _keys_examined, _docs_examined = self._run_query(query)
    +        return len(documents)
    +
    +    def explain(self, query: dict[str, Any] | None = None) -> dict[str, Any]:
    +        """Return the winning Mongo-shaped plan and actual scan counters."""
    +
    +        normalized = {} if query is None else query
    +        documents, plan, keys_examined, docs_examined = self._run_query(normalized)
    +        return {
    +            "queryPlanner": {"winningPlan": plan.summary(normalized)},
    +            "executionStats": {
    +                "nReturned": len(documents),
    +                "keysExamined": keys_examined,
    +                "docsExamined": docs_examined,
    +            },
    +        }
    +
    +    def aggregate(self, pipeline: list[dict[str, Any]]) -> list[dict[str, Any]]:
    +        """Run the minimum aggregation pipeline against a stable snapshot."""
    +
    +        return execute_pipeline(self._documents, pipeline)

         def update_one(
             self, query: dict[str, Any], update: dict[str, Any]
    @@ -135,6 +254,8 @@ class Collection:
                 matched += 1
                 candidate = apply_operator_update(original, update)
                 if not bson_equal(candidate, original):
    +                for index in self._indexes.values():
    +                    index.validate_replace(original, candidate)
                     self.oplog.emit(
                         self.name,
                         "update",
    @@ -159,6 +280,8 @@ class Collection:
                     candidate = replacement_document(original, replacement)
                     modified = not bson_equal(candidate, original)
                     if modified:
    +                    for index in self._indexes.values():
    +                        index.validate_replace(original, candidate)
                         self.oplog.emit(
                             self.name,
                             "replace",
    @@ -183,6 +306,8 @@ class Collection:
                 if matches(document, query) and (limit is None or deleted < limit):
                     self.oplog.emit(self.name, "delete", document["_id"])
                     self._id_index.remove(document["_id"])
    +                for index in self._indexes.values():
    +                    index.remove(document)
                     self._documents.pop(position)
                     deleted += 1
                 else:
    @@ -190,9 +315,40 @@ class Collection:
             return DeleteResult(deleted)

         def _replace_at(self, position: int, document: dict[str, Any]) -> None:
    -        key = self._documents[position]["_id"]
    +        original = self._documents[position]
    +        key = original["_id"]
             self._documents[position] = document
             self._id_index.replace(key, document)
    +        for index in self._indexes.values():
    +            index.replace(original, document)
    +
    +    def _run_query(
    +        self, query: dict[str, Any] | None
    +    ) -> tuple[list[dict[str, Any]], Plan, int, int]:
    +        normalized = {} if query is None else query
    +        # Validate query syntax even on an empty collection or zero-candidate scan.
    +        matches({}, normalized)
    +        plan = choose_plan(
    +            normalized,
    +            len(self._documents),
    +            self._indexes.values(),
    +            self._id_index,
    +        )
    +        if plan.candidate_ids is None:
    +            candidates = self._documents
    +            keys_examined = 0
    +        else:
    +            candidate_ids = plan.candidate_ids
    +            # Index buckets are unordered ownership sets; walking storage order
    +            # preserves the deterministic public result contract.
    +            candidates = [
    +                document
    +                for document in self._documents
    +                if canonical_key(document["_id"]) in candidate_ids
    +            ]
    +            keys_examined = plan.keys_examined
    +        matched = [document for document in candidates if matches(document, normalized)]
    +        return matched, plan, keys_examined, len(candidates)

         @staticmethod
         def _post_image_update(
    @@ -221,6 +377,10 @@ class Collection:
         def _apply_oplog_entry(self, entry: OplogEntry) -> None:
             """Recovery-only mutation path; deliberately emits no recursive log."""

    +        if entry.operation == "create_index":
    +            assert entry.payload is not None
    +            self._restore_index(entry.payload)
    +            return
             existing = self._id_index.get(entry.key)
             if entry.operation in {"insert", "replace"}:
                 assert entry.payload is not None
    @@ -228,6 +388,8 @@ class Collection:
                 if existing is None:
                     self._documents.append(candidate)
                     self._id_index.add(candidate)
    +                for index in self._indexes.values():
    +                    index.add(candidate)
                 else:
                     position = self._documents.index(existing)
                     self._replace_at(position, candidate)
    @@ -240,6 +402,8 @@ class Collection:
                 self._replace_at(position, candidate)
             elif entry.operation == "delete":
                 if existing is not None:
    +                for index in self._indexes.values():
    +                    index.remove(existing)
                     self._documents.remove(existing)
                     self._id_index.remove(entry.key)
             else:
    ```

??? note "文件差异：src/minimongodb/database.py"
    ```diff
    diff --git a/src/minimongodb/database.py b/src/minimongodb/database.py
    index 0a717669bc1207005dce8f5a79cd305c66f86945..a6d05a93a3788da472450ec1645ab27661bd61aa 100644
    --- a/src/minimongodb/database.py
    +++ b/src/minimongodb/database.py
    @@ -51,6 +51,7 @@ class Database:
                 listener=self._journal.append,
             )
             names = set(recovery.collections)
    +        names.update(recovery.indexes)
             names.update(entry.collection for entry in recovery.journal_entries)
             self._collections = {
                 name: Collection(
    @@ -66,6 +67,10 @@ class Database:
                     collection._apply_oplog_entry(
                         OplogEntry(0, name, "insert", document["_id"], document)
                     )
    +        for name, definitions in recovery.indexes.items():
    +            collection = self._collections[name]
    +            for definition in definitions:
    +                collection._restore_index(definition)
             replay(
                 recovery.journal_entries,
                 self._collections,
    @@ -95,6 +100,10 @@ class Database:
                         name: collection.find()
                         for name, collection in sorted(self._collections.items())
                     },
    +                "indexes": {
    +                    name: collection._index_definitions()
    +                    for name, collection in sorted(self._collections.items())
    +                },
                 },
             )

    ```

??? note "文件差异：src/minimongodb/errors.py"
    ```diff
    diff --git a/src/minimongodb/errors.py b/src/minimongodb/errors.py
    index 1a8275c064e10ec623c7f278b62c07a402d11ede..9f4fd263e66366f4acbc1c9fb6f2d32176023c9e 100644
    --- a/src/minimongodb/errors.py
    +++ b/src/minimongodb/errors.py
    @@ -21,6 +21,10 @@ class InvalidUpdateError(MiniMongoError):
         """Raised for malformed updates or incompatible operand types."""


    +class InvalidPipelineError(MiniMongoError):
    +    """Raised for malformed or unsupported aggregation pipeline stages."""
    +
    +
     class PathError(MiniMongoError):
         """Raised when a dotted path cannot traverse the current container."""

    ```

??? note "文件差异：src/minimongodb/index/id_index.py"
    ```diff
    diff --git a/src/minimongodb/index/id_index.py b/src/minimongodb/index/id_index.py
    index ce512aeff2f2953345feea81256d61c8bb039961..6513550fd2dfc0fc9836efdc8e87dd12df226555 100644
    --- a/src/minimongodb/index/id_index.py
    +++ b/src/minimongodb/index/id_index.py
    @@ -38,3 +38,12 @@ class IdIndex:
                 return canonical_key(key) in self._documents
             except TypeError:
                 return False
    +
    +    @property
    +    def has_root_array(self) -> bool:
    +        """Whether scalar matcher semantics can fan out inside an ``_id``."""
    +
    +        return any(
    +            isinstance(document["_id"], list)
    +            for document in self._documents.values()
    +        )
    ```

??? note "文件差异：src/minimongodb/index/secondary.py"
    ```diff
    diff --git a/src/minimongodb/index/secondary.py b/src/minimongodb/index/secondary.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..f3f2438aa80e939e9fccc22e2e5a63286c60f3ba
    --- /dev/null
    +++ b/src/minimongodb/index/secondary.py
    @@ -0,0 +1,297 @@
    +"""Canonical ordered secondary indexes with explicit multikey expansion.
    +
    +One document can own several index entries when a selected value is an array.
    +Entries retain their BSON-shaped values for ordered scans, while ownership and
    +uniqueness use the same type-tagged ``canonical_key`` representation as
    +``_id``.  This separation keeps comparison order and equality identity honest.
    +"""
    +
    +from __future__ import annotations
    +
    +from itertools import product
    +from typing import Any, Iterable
    +
    +from minimongodb.bson import bson_compare, bson_equal, canonical_key
    +from minimongodb.errors import DuplicateKeyError
    +CompoundKey = tuple[tuple[Any, ...], ...]
    +DocumentKey = tuple[Any, ...]
    +
    +
    +def normalize_index_spec(
    +    keys: str | dict[str, int] | Iterable[tuple[str, int]],
    +) -> tuple[tuple[str, int], ...]:
    +    """Normalize the public shorthand to an ordered ascending key pattern."""
    +
    +    if isinstance(keys, str):
    +        items = [(keys, 1)]
    +    elif isinstance(keys, dict):
    +        items = list(keys.items())
    +    else:
    +        try:
    +            items = list(keys)
    +        except TypeError as error:
    +            raise TypeError("index keys must be a field or ordered key pairs") from error
    +    if not items:
    +        raise ValueError("an index needs at least one field")
    +    if any(
    +        not isinstance(item, tuple)
    +        or len(item) != 2
    +        or not isinstance(item[0], str)
    +        or not item[0]
    +        or item[1] != 1
    +        for item in items
    +    ):
    +        raise ValueError("only non-empty ascending field paths are supported")
    +    fields = [field for field, _direction in items]
    +    if len(set(fields)) != len(fields):
    +        raise ValueError("an index cannot repeat a field path")
    +    return tuple(items)
    +
    +
    +def default_index_name(spec: tuple[tuple[str, int], ...]) -> str:
    +    return "_".join(f"{field}_{direction}" for field, direction in spec)
    +
    +
    +def _leaves(value: Any) -> list[Any]:
    +    if isinstance(value, list):
    +        return [leaf for child in value for leaf in _leaves(child)]
    +    return [value]
    +
    +
    +def _field_values(document: dict[str, Any], path: str) -> tuple[list[Any], bool]:
    +    selected, traversed_array = _resolve_index_path(document, path.split("."))
    +    if not selected:
    +        # Like a non-sparse MongoDB index, missing fields occupy a null-like key.
    +        return [None], traversed_array
    +    values = [leaf for value in selected for leaf in _leaves(value)]
    +    expanded_value = any(isinstance(value, list) for value in selected)
    +    return values or [None], traversed_array or expanded_value
    +
    +
    +def _resolve_index_path(
    +    current: Any, parts: list[str]
    +) -> tuple[list[Any], bool]:
    +    if not parts:
    +        return [current], isinstance(current, list)
    +    part, rest = parts[0], parts[1:]
    +    if isinstance(current, dict):
    +        if part not in current:
    +            return [], False
    +        return _resolve_index_path(current[part], rest)
    +    if isinstance(current, list):
    +        if part.isdigit():
    +            position = int(part)
    +            if position >= len(current):
    +                return [], True
    +            values, _child_array = _resolve_index_path(current[position], rest)
    +            return values, True
    +        values: list[Any] = []
    +        for element in current:
    +            selected, _child_array = _resolve_index_path(element, parts)
    +            values.extend(selected)
    +        return values, True
    +    return [], False
    +
    +
    +class SecondaryIndex:
    +    """An ordered key pattern backed by canonical buckets of document ids."""
    +
    +    def __init__(
    +        self,
    +        spec: tuple[tuple[str, int], ...],
    +        *,
    +        name: str,
    +        unique: bool = False,
    +    ) -> None:
    +        self.spec = spec
    +        self.name = name
    +        self.unique = unique
    +        self.is_multikey = False
    +        self._values: dict[CompoundKey, tuple[Any, ...]] = {}
    +        self._owners: dict[CompoundKey, set[DocumentKey]] = {}
    +
    +    @property
    +    def key_pattern(self) -> dict[str, int]:
    +        return dict(self.spec)
    +
    +    @property
    +    def entry_count(self) -> int:
    +        return len(self._owners)
    +
    +    def document_keys(
    +        self, document: dict[str, Any]
    +    ) -> list[tuple[CompoundKey, tuple[Any, ...]]]:
    +        entries, _multikey = self._document_entries(document)
    +        return entries
    +
    +    def _document_entries(
    +        self, document: dict[str, Any]
    +    ) -> tuple[list[tuple[CompoundKey, tuple[Any, ...]]], bool]:
    +        selected = [
    +            _field_values(document, field) for field, _direction in self.spec
    +        ]
    +        combinations = product(*(values for values, _expanded in selected))
    +        deduplicated: dict[CompoundKey, tuple[Any, ...]] = {}
    +        for values in combinations:
    +            compound = tuple(canonical_key(value) for value in values)
    +            deduplicated.setdefault(compound, values)
    +        return list(deduplicated.items()), any(
    +            expanded for _values, expanded in selected
    +        )
    +
    +    def validate_documents(self, documents: Iterable[dict[str, Any]]) -> None:
    +        """Check a prospective batch without making any entry visible."""
    +
    +        if not self.unique:
    +            return
    +        owners = {key: set(value) for key, value in self._owners.items()}
    +        for document in documents:
    +            document_id = canonical_key(document["_id"])
    +            for compound, values in self.document_keys(document):
    +                conflicting = owners.get(compound, set()) - {document_id}
    +                if conflicting:
    +                    raise DuplicateKeyError(
    +                        f"duplicate key for index {self.name}: {values!r}"
    +                    )
    +                owners.setdefault(compound, set()).add(document_id)
    +
    +    def validate_replace(
    +        self, original: dict[str, Any], replacement: dict[str, Any]
    +    ) -> None:
    +        if not self.unique:
    +            return
    +        original_id = canonical_key(original["_id"])
    +        for compound, values in self.document_keys(replacement):
    +            conflicting = self._owners.get(compound, set()) - {original_id}
    +            if conflicting:
    +                raise DuplicateKeyError(
    +                    f"duplicate key for index {self.name}: {values!r}"
    +                )
    +
    +    def add(self, document: dict[str, Any]) -> None:
    +        entries, expanded_array = self._document_entries(document)
    +        if expanded_array:
    +            self.is_multikey = True
    +        document_id = canonical_key(document["_id"])
    +        for compound, values in entries:
    +            self._values.setdefault(compound, values)
    +            self._owners.setdefault(compound, set()).add(document_id)
    +
    +    def remove(self, document: dict[str, Any]) -> None:
    +        document_id = canonical_key(document["_id"])
    +        for compound, _values in self.document_keys(document):
    +            owners = self._owners.get(compound)
    +            if owners is None:
    +                continue
    +            owners.discard(document_id)
    +            if not owners:
    +                self._owners.pop(compound)
    +                self._values.pop(compound)
    +
    +    def replace(
    +        self, original: dict[str, Any], replacement: dict[str, Any]
    +    ) -> None:
    +        self.remove(original)
    +        self.add(replacement)
    +
    +    def prefix_length(self, query: dict[str, Any]) -> int:
    +        """Return the usable leftmost prefix, stopping after a range predicate."""
    +
    +        length = 0
    +        for field, _direction in self.spec:
    +            if field not in query or field.startswith("$"):
    +                break
    +            condition = query[field]
    +            if self.is_multikey and isinstance(condition, list):
    +                break
    +            if isinstance(condition, dict):
    +                operators = set(condition)
    +                if not operators or any(not key.startswith("$") for key in operators):
    +                    length += 1
    +                    continue
    +                if not operators <= {"$eq", "$in", "$gt", "$gte", "$lt", "$lte"}:
    +                    break
    +                if self.is_multikey and (
    +                    len(operators) > 1
    +                    or any(
    +                        (
    +                            operator == "$in"
    +                            and isinstance(operand, list)
    +                            and any(isinstance(option, list) for option in operand)
    +                        )
    +                        or (operator != "$in" and isinstance(operand, list))
    +                        for operator, operand in condition.items()
    +                    )
    +                ):
    +                    # Without $elemMatch, different array elements may satisfy
    +                    # different predicates. Leaf-key intersection would drop
    +                    # valid documents, so correctness requires a collection scan.
    +                    break
    +                length += 1
    +                if operators - {"$eq", "$in"}:
    +                    break
    +            else:
    +                length += 1
    +        return length
    +
    +    def scan(
    +        self, query: dict[str, Any], prefix_length: int
    +    ) -> tuple[set[DocumentKey], int]:
    +        """Scan matching ordered keys and return candidate owners plus key count."""
    +
    +        candidates: set[DocumentKey] = set()
    +        keys_examined = 0
    +        for compound in sorted(self._owners, key=self._sort_token):
    +            values = self._values[compound]
    +            if all(
    +                _condition_matches(values[position], query[field])
    +                for position, (field, _direction) in enumerate(
    +                    self.spec[:prefix_length]
    +                )
    +            ):
    +                keys_examined += 1
    +                candidates.update(self._owners[compound])
    +        return candidates, keys_examined
    +
    +    def _sort_token(self, compound: CompoundKey) -> "_CompoundSort":
    +        return _CompoundSort(self._values[compound])
    +
    +
    +class _CompoundSort:
    +    """Small comparison wrapper so ordered scans use BSON comparison."""
    +
    +    def __init__(self, values: tuple[Any, ...]) -> None:
    +        self.values = values
    +
    +    def __lt__(self, other: "_CompoundSort") -> bool:
    +        for left, right in zip(self.values, other.values):
    +            compared = bson_compare(left, right)
    +            if compared:
    +                return compared < 0
    +        return len(self.values) < len(other.values)
    +
    +
    +def _condition_matches(value: Any, condition: Any) -> bool:
    +    if not isinstance(condition, dict) or not any(
    +        isinstance(key, str) and key.startswith("$") for key in condition
    +    ):
    +        return bson_equal(value, condition)
    +    for operator, operand in condition.items():
    +        if operator == "$eq" and not bson_equal(value, operand):
    +            return False
    +        if operator == "$in":
    +            if not isinstance(operand, list) or not any(
    +                bson_equal(value, option) for option in operand
    +            ):
    +                return False
    +        if operator in {"$gt", "$gte", "$lt", "$lte"}:
    +            compared = bson_compare(value, operand)
    +            accepted = {
    +                "$gt": compared > 0,
    +                "$gte": compared >= 0,
    +                "$lt": compared < 0,
    +                "$lte": compared <= 0,
    +            }[operator]
    +            if not accepted:
    +                return False
    +    return True
    ```

??? note "文件差异：src/minimongodb/plan/__init__.py"
    ```diff
    diff --git a/src/minimongodb/plan/__init__.py b/src/minimongodb/plan/__init__.py
    index b53988c97a7ffa4f36e494cf9453e82d7b29a5eb..012e3178515b102c4bd0ec3a5662ce55795b02d2 100644
    --- a/src/minimongodb/plan/__init__.py
    +++ b/src/minimongodb/plan/__init__.py
    @@ -1,7 +1,135 @@
    -"""M2 placeholder for COLLSCAN/IXSCAN planning and ``explain``.
    +"""Deterministic COLLSCAN/IXSCAN planning with observable execution counts.

    -M1 always scans the deterministic in-memory document list, except that the
    -private ``_id`` map enforces uniqueness and supports recovery identity lookup.
    -M2 will add plan nodes, selection estimates, secondary-index scans, and public
    -explain statistics.  No callable planner is exposed early.
    +The estimate is intentionally small: each prefix-compatible index reports the
    +number of candidate documents for the query bounds.  An IXSCAN wins only when
    +it examines fewer documents than a collection scan, with deterministic ties by
    +candidate count, longer compound prefix, then index name.
     """
    +
    +from __future__ import annotations
    +
    +from dataclasses import dataclass
    +from typing import Any, Iterable
    +
    +from minimongodb.bson import canonical_key
    +from minimongodb.index import IdIndex, SecondaryIndex
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class Plan:
    +    stage: str
    +    index: SecondaryIndex | None = None
    +    prefix_length: int = 0
    +    candidate_ids: set[tuple[Any, ...]] | None = None
    +    keys_examined: int = 0
    +    summary_override: dict[str, Any] | None = None
    +
    +    def summary(self, query: dict[str, Any]) -> dict[str, Any]:
    +        if self.summary_override is not None:
    +            return self.summary_override
    +        if self.index is None:
    +            return {"stage": "COLLSCAN"}
    +        fields = [field for field, _direction in self.index.spec[: self.prefix_length]]
    +        return {
    +            "stage": "IXSCAN",
    +            "indexName": self.index.name,
    +            "keyPattern": self.index.key_pattern,
    +            "indexBounds": {field: query[field] for field in fields},
    +        }
    +
    +
    +def choose_plan(
    +    query: dict[str, Any],
    +    document_count: int,
    +    indexes: Iterable[SecondaryIndex],
    +    id_index: IdIndex | None = None,
    +) -> Plan:
    +    id_values = _id_lookup_values(query)
    +    if (
    +        id_index is not None
    +        and id_index.has_root_array
    +        and not _id_lookup_is_safe_with_array_ids(query)
    +    ):
    +        id_values = None
    +    if id_index is not None and id_values is not None:
    +        candidate_ids = {
    +            canonical_key(document["_id"])
    +            for value in id_values
    +            if (document := id_index.get(value)) is not None
    +        }
    +        return Plan(
    +            "IXSCAN",
    +            candidate_ids=candidate_ids,
    +            keys_examined=len(id_values),
    +            summary_override={
    +                "stage": "IXSCAN",
    +                "indexName": "_id_",
    +                "keyPattern": {"_id": 1},
    +                "indexBounds": {"_id": query["_id"]},
    +            },
    +        )
    +    candidates: list[tuple[int, int, str, SecondaryIndex, set, int]] = []
    +    for index in indexes:
    +        prefix_length = index.prefix_length(query)
    +        if not prefix_length:
    +            continue
    +        document_ids, keys_examined = index.scan(query, prefix_length)
    +        candidates.append(
    +            (
    +                len(document_ids),
    +                -prefix_length,
    +                index.name,
    +                index,
    +                document_ids,
    +                keys_examined,
    +            )
    +        )
    +    if not candidates:
    +        return Plan("COLLSCAN")
    +    estimate, negative_prefix, _name, index, document_ids, keys_examined = min(
    +        candidates, key=lambda candidate: candidate[:3]
    +    )
    +    if estimate >= document_count:
    +        return Plan("COLLSCAN")
    +    return Plan(
    +        "IXSCAN",
    +        index=index,
    +        prefix_length=-negative_prefix,
    +        candidate_ids=document_ids,
    +        keys_examined=keys_examined,
    +    )
    +
    +
    +def _id_lookup_values(query: dict[str, Any]) -> list[Any] | None:
    +    if "_id" not in query:
    +        return None
    +    condition = query["_id"]
    +    if isinstance(condition, dict) and any(
    +        isinstance(key, str) and key.startswith("$") for key in condition
    +    ):
    +        if set(condition) == {"$eq"}:
    +            return [condition["$eq"]]
    +        if set(condition) == {"$in"} and isinstance(condition["$in"], list):
    +            return condition["$in"]
    +        return None
    +    return [condition]
    +
    +
    +def _id_lookup_is_safe_with_array_ids(query: dict[str, Any]) -> bool:
    +    if "_id" not in query:
    +        return True
    +    condition = query["_id"]
    +    if isinstance(condition, dict) and any(
    +        isinstance(key, str) and key.startswith("$") for key in condition
    +    ):
    +        if set(condition) == {"$eq"}:
    +            return isinstance(condition["$eq"], (dict, list))
    +        if set(condition) == {"$in"} and isinstance(condition["$in"], list):
    +            return all(
    +                isinstance(option, (dict, list)) for option in condition["$in"]
    +            )
    +        return False
    +    return isinstance(condition, (dict, list))
    +
    +
    +__all__ = ["Plan", "choose_plan"]
    ```

??? note "文件差异：src/minimongodb/storage/recovery.py"
    ```diff
    diff --git a/src/minimongodb/storage/recovery.py b/src/minimongodb/storage/recovery.py
    index 27b52dea82fdc285a5905a16f9b4c7222f12aca9..f07b27cb6332c8def61b4cb61770458064029e91 100644
    --- a/src/minimongodb/storage/recovery.py
    +++ b/src/minimongodb/storage/recovery.py
    @@ -15,6 +15,7 @@ from minimongodb.storage.journal import Journal
     class RecoveryState:
         checkpoint_sequence: int
         collections: dict[str, list[dict[str, Any]]]
    +    indexes: dict[str, list[dict[str, Any]]]
         journal_entries: list[OplogEntry]


    @@ -25,9 +26,11 @@ def load_recovery_state(directory: str | Path) -> RecoveryState:
         checkpoint = read_checkpoint(root / "checkpoint.bin") or {
             "sequence": 0,
             "collections": {},
    +        "indexes": {},
         }
         return RecoveryState(
             checkpoint_sequence=checkpoint["sequence"],
             collections=checkpoint["collections"],
    +        indexes=checkpoint.get("indexes", {}),
             journal_entries=Journal(root / "journal.bin").read_entries(repair=True),
         )
    ```

**是什么，为什么现在需要**

索引把 Canonical Key 映射到 Candidate，Plan 显式选择 COLLSCAN 或 IXSCAN，Aggregation Pipeline 则组合有序的流式或阻塞文档算子。

**在运行时做什么**

写入在发布前暂存全部索引项；读取取回并重检计划候选；随后聚合把受控文档依次传过每个已校验 Stage。

**关键语句理解**

访问路径不能取代谓词重检，Pipeline 顺序也必须可观察；这些边界防止优化改变文档语义。

#### 包、Fixture 与工程支撑

保持包导出、测试语料、依赖与运行环境可复现。

??? note "支撑文件差异（1 个文件）"
    **`src/minimongodb/index/__init__.py`**

    ```diff
    diff --git a/src/minimongodb/index/__init__.py b/src/minimongodb/index/__init__.py
    index 33e63b12571722e877bb78200e64c27ae7776e30..6ed013890b4f3af070f0041003ba85cfd03e4e5f 100644
    --- a/src/minimongodb/index/__init__.py
    +++ b/src/minimongodb/index/__init__.py
    @@ -1,5 +1,15 @@
    -"""Index boundaries; M1 implements only the mandatory unique ``_id`` index."""
    +"""Canonical identity and secondary index structures."""

     from minimongodb.index.id_index import IdIndex
    +from minimongodb.index.secondary import (
    +    SecondaryIndex,
    +    default_index_name,
    +    normalize_index_spec,
    +)

    -__all__ = ["IdIndex"]
    +__all__ = [
    +    "IdIndex",
    +    "SecondaryIndex",
    +    "default_index_name",
    +    "normalize_index_spec",
    +]
    ```


### 验证证据

运行 `uv run pytest -q $(cat journey/stages/06-indexes-plans-pipelines/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

访问路径不能取代谓词重检，Pipeline 顺序也必须可观察；这些边界防止优化改变文档语义。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 8 章](https://github.com/system-in-miniature/mini-mongodb/blob/main/docs/zh/tutorial/08-planner-explain.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-mongodb/blob/main/journey/stages/06-indexes-plans-pipelines/stage.patch)
