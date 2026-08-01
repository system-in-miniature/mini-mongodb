# Stage 02 · 数组感知的查询匹配

### 目标

实现数组感知的查询匹配，并能从可执行反例、运行时状态与关键语句解释其边界。

??? note "交付文件"
    - `src/minimongodb/query/__init__.py`
    - `src/minimongodb/query/matcher.py`
    - `tests/test_array_matching.py`
    - `tests/test_query.py`

### 当前遇到的问题

点路径与数组会让查询文档产生歧义，必须区分标量逐元素匹配与复合值精确相等。

### 测试契约

#### 先看会坏在哪里

反例比较标量对数组匹配、字面数组顺序、嵌入文档精确匹配、点路径展开、逻辑分支与未知算子。

??? note "文件差异：tests/test_array_matching.py"
    ```diff
    diff --git a/tests/test_array_matching.py b/tests/test_array_matching.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..e3e8dba1e2e45cc762da95ef9d9b27e5bf5e685e
    --- /dev/null
    +++ b/tests/test_array_matching.py
    @@ -0,0 +1,34 @@
    +"""The project's central lesson: arrays fan out, literal documents do not."""
    +
    +from minimongodb.query import matches
    +
    +
    +def test_scalar_equality_automatically_matches_an_array_element() -> None:
    +    assert matches({"tags": ["database", "python"]}, {"tags": "python"})
    +    assert not matches({"tags": ["database", "python"]}, {"tags": "rust"})
    +
    +
    +def test_scalar_comparison_automatically_matches_an_array_element() -> None:
    +    assert matches({"scores": [2, 8]}, {"scores": {"$gt": 7}})
    +
    +
    +def test_literal_array_still_requires_whole_array_equality() -> None:
    +    document = {"tags": ["database", "python"]}
    +    assert matches(document, {"tags": ["database", "python"]})
    +    assert not matches(document, {"tags": ["python", "database"]})
    +
    +
    +def test_nested_document_literal_is_an_exact_whole_value_match() -> None:
    +    document = {"profile": {"name": "Ada", "city": "London"}}
    +    assert not matches(document, {"profile": {"name": "Ada"}})
    +    assert matches(document, {"profile": {"name": "Ada", "city": "London"}})
    +
    +
    +def test_dotted_path_selects_inside_nested_document_instead() -> None:
    +    document = {"profile": {"name": "Ada", "city": "London"}}
    +    assert matches(document, {"profile.name": "Ada"})
    +
    +
    +def test_dotted_path_fans_out_through_arrays_of_documents() -> None:
    +    document = {"items": [{"sku": "A"}, {"sku": "B"}]}
    +    assert matches(document, {"items.sku": "B"})
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

反例比较标量对数组匹配、字面数组顺序、嵌入文档精确匹配、点路径展开、逻辑分支与未知算子。

**关键测试语句**

```python
assert matches({"tags": ["database", "python"]}, {"tags": "python"})
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/test_query.py"
    ```diff
    diff --git a/tests/test_query.py b/tests/test_query.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..9f0a512137586174fa20becbe26c1df9e8c45e42
    --- /dev/null
    +++ b/tests/test_query.py
    @@ -0,0 +1,37 @@
    +"""Query operator contract independent of collection storage."""
    +
    +import pytest
    +
    +from minimongodb.errors import InvalidQueryError
    +from minimongodb.query import matches
    +
    +
    +@pytest.mark.parametrize(
    +    ("query", "expected"),
    +    [
    +        ({"age": 20}, True),
    +        ({"age": {"$eq": 20}}, True),
    +        ({"age": {"$gt": 19, "$lte": 20}}, True),
    +        ({"age": {"$gte": 20, "$lt": 21}}, True),
    +        ({"age": {"$ne": 21}}, True),
    +        ({"age": {"$in": [10, 20]}}, True),
    +        ({"missing": {"$exists": False}}, True),
    +        ({"age": {"$exists": True}}, True),
    +        ({"$and": [{"age": 20}, {"name": "Ada"}]}, True),
    +        ({"$or": [{"age": 99}, {"name": "Ada"}]}, True),
    +        ({"age": {"$not": {"$gt": 20}}}, True),
    +        ({"$not": {"name": "Grace"}}, True),
    +        ({"age": {"$lt": 20}}, False),
    +    ],
    +)
    +def test_query_operators(query: dict, expected: bool) -> None:
    +    assert matches({"name": "Ada", "age": 20}, query) is expected
    +
    +
    +def test_ne_matches_a_missing_field() -> None:
    +    assert matches({}, {"age": {"$ne": 20}})
    +
    +
    +def test_unknown_operator_is_rejected() -> None:
    +    with pytest.raises(InvalidQueryError):
    +        matches({"age": 20}, {"age": {"$wat": 20}})
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

反例比较标量对数组匹配、字面数组顺序、嵌入文档精确匹配、点路径展开、逻辑分支与未知算子。

**关键测试语句**

```python
assert matches({"tags": ["database", "python"]}, {"tags": "python"})
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

查询是递归谓词树。字段解析可以穿过数组展开，而字面 List 或 Document 仍是一个精确 BSON 值。

### 为什么需要这个机制

点路径与数组会让查询文档产生歧义，必须区分标量逐元素匹配与复合值精确相等。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Matcher 解析候选值、对它们应用字段算子，再组合逻辑子句，全程不修改文档。

### 机制板块

#### 数组感知的查询匹配机制

Matcher 解析候选值、对它们应用字段算子，再组合逻辑子句，全程不修改文档。

??? note "文件差异：src/minimongodb/query/matcher.py"
    ```diff
    diff --git a/src/minimongodb/query/matcher.py b/src/minimongodb/query/matcher.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..e37eb05373517792a5fc6c76e2e9f79e95873230
    --- /dev/null
    +++ b/src/minimongodb/query/matcher.py
    @@ -0,0 +1,148 @@
    +"""Query matcher with deliberate separation of path fan-out and equality.
    +
    +The crucial distinction is easy to lose in one clever recursive function:
    +
    +* traversing a dotted path may fan out through an array of documents;
    +* comparing a scalar to an array may inspect each array element;
    +* comparing a literal document or array remains exact whole-value equality.
    +
    +Keeping these steps separate makes the MongoDB-specific behavior visible.
    +"""
    +
    +from __future__ import annotations
    +
    +from collections.abc import Iterable
    +from typing import Any
    +
    +from minimongodb.bson import MISSING, bson_compare, bson_equal
    +from minimongodb.errors import InvalidQueryError
    +
    +
    +def resolve_path(document: Any, path: str) -> list[Any]:
    +    """Return every value selected by a dotted path, fanning out through arrays."""
    +
    +    if not isinstance(path, str) or not path or any(not p for p in path.split(".")):
    +        raise InvalidQueryError("field path must have non-empty segments")
    +    return _resolve(document, path.split("."))
    +
    +
    +def _resolve(current: Any, parts: list[str]) -> list[Any]:
    +    if not parts:
    +        return [current]
    +    part, rest = parts[0], parts[1:]
    +    if isinstance(current, dict):
    +        if part not in current:
    +            return []
    +        return _resolve(current[part], rest)
    +    if isinstance(current, list):
    +        if part.isdigit():
    +            position = int(part)
    +            return _resolve(current[position], rest) if position < len(current) else []
    +        # Do not consume the part: each element must still resolve that field.
    +        return [
    +            value
    +            for element in current
    +            for value in _resolve(element, parts)
    +        ]
    +    return []
    +
    +
    +def _array_candidates(value: Any, expected: Any) -> Iterable[Any]:
    +    """Expand stored arrays only when the query operand is scalar-like."""
    +
    +    if isinstance(value, list) and not isinstance(expected, (list, dict)):
    +        for item in value:
    +            # Nested arrays also expose scalar leaves for this teaching subset.
    +            yield from _array_candidates(item, expected)
    +    else:
    +        yield value
    +
    +
    +def _equals(value: Any, expected: Any) -> bool:
    +    return any(bson_equal(candidate, expected) for candidate in _array_candidates(value, expected))
    +
    +
    +def _compare(value: Any, expected: Any, operator: str) -> bool:
    +    def accepted(candidate: Any) -> bool:
    +        compared = bson_compare(candidate, expected)
    +        return {
    +            "$gt": compared > 0,
    +            "$gte": compared >= 0,
    +            "$lt": compared < 0,
    +            "$lte": compared <= 0,
    +        }[operator]
    +
    +    try:
    +        return any(accepted(candidate) for candidate in _array_candidates(value, expected))
    +    except TypeError:
    +        return False
    +
    +
    +def _operator_matches(values: list[Any], operator: str, operand: Any) -> bool:
    +    present = bool(values)
    +    if operator == "$exists":
    +        if not isinstance(operand, bool):
    +            raise InvalidQueryError("$exists requires a boolean")
    +        return present is operand
    +    if operator == "$ne":
    +        return not any(_equals(value, operand) for value in values)
    +    if operator == "$not":
    +        if not isinstance(operand, dict):
    +            raise InvalidQueryError("$not requires an operator document")
    +        return not _field_matches(values, operand)
    +    if not present:
    +        return False
    +    if operator == "$eq":
    +        return any(_equals(value, operand) for value in values)
    +    if operator in {"$gt", "$gte", "$lt", "$lte"}:
    +        return any(_compare(value, operand, operator) for value in values)
    +    if operator == "$in":
    +        if not isinstance(operand, list):
    +            raise InvalidQueryError("$in requires an array")
    +        return any(
    +            _equals(value, option) for value in values for option in operand
    +        )
    +    raise InvalidQueryError(f"unsupported query operator: {operator}")
    +
    +
    +def _field_matches(values: list[Any], condition: Any) -> bool:
    +    if isinstance(condition, dict) and any(
    +        isinstance(key, str) and key.startswith("$") for key in condition
    +    ):
    +        if not all(isinstance(key, str) and key.startswith("$") for key in condition):
    +            raise InvalidQueryError("cannot mix operators and literal fields")
    +        return all(
    +            _operator_matches(values, operator, operand)
    +            for operator, operand in condition.items()
    +        )
    +    return bool(values) and any(_equals(value, condition) for value in values)
    +
    +
    +def matches(document: dict[str, Any], query: dict[str, Any] | None = None) -> bool:
    +    """Return whether a document satisfies the supported Mongo-shaped query."""
    +
    +    if query is None:
    +        query = {}
    +    if not isinstance(query, dict):
    +        raise InvalidQueryError("query must be a document")
    +    for key, condition in query.items():
    +        if key == "$and":
    +            if not isinstance(condition, list):
    +                raise InvalidQueryError("$and requires an array")
    +            if not all(matches(document, child) for child in condition):
    +                return False
    +        elif key == "$or":
    +            if not isinstance(condition, list):
    +                raise InvalidQueryError("$or requires an array")
    +            if not any(matches(document, child) for child in condition):
    +                return False
    +        elif key == "$not":
    +            if not isinstance(condition, dict):
    +                raise InvalidQueryError("$not requires a query document")
    +            if matches(document, condition):
    +                return False
    +        elif key.startswith("$"):
    +            raise InvalidQueryError(f"unsupported logical operator: {key}")
    +        elif not _field_matches(resolve_path(document, key), condition):
    +            return False
    +    return True
    ```

**是什么，为什么现在需要**

查询是递归谓词树。字段解析可以穿过数组展开，而字面 List 或 Document 仍是一个精确 BSON 值。

**在运行时做什么**

Matcher 解析候选值、对它们应用字段算子，再组合逻辑子句，全程不修改文档。

**关键语句理解**

把遍历与相等分开，可防止部分嵌入文档悄悄变成点字段查询。

#### 包、Fixture 与工程支撑

保持包导出、测试语料、依赖与运行环境可复现。

??? note "支撑文件差异（1 个文件）"
    **`src/minimongodb/query/__init__.py`**

    ```diff
    diff --git a/src/minimongodb/query/__init__.py b/src/minimongodb/query/__init__.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..50d90024afacb17c66697886dcad913cc9904af5
    --- /dev/null
    +++ b/src/minimongodb/query/__init__.py
    @@ -0,0 +1,5 @@
    +"""Mongo-shaped query matching over in-memory teaching documents."""
    +
    +from minimongodb.query.matcher import matches, resolve_path
    +
    +__all__ = ["matches", "resolve_path"]
    ```


### 验证证据

运行 `uv run pytest -q $(cat journey/stages/02-array-aware-queries/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

把遍历与相等分开，可防止部分嵌入文档悄悄变成点字段查询。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 3 章](https://github.com/system-in-miniature/mini-mongodb/blob/main/docs/zh/tutorial/03-queries.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-mongodb/blob/main/journey/stages/02-array-aware-queries/stage.patch)
