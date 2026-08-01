# Stage 07 · 规划前的查询校验

### 目标

实现规划前的查询校验，并能从可执行反例、运行时状态与关键语句解释其边界。

??? note "交付文件"
    - `src/minimongodb/query/__init__.py`
    - `src/minimongodb/query/matcher.py`
    - `tests/test_query.py`

### 当前遇到的问题

若只在匹配文档时校验，非法查询会在空集合或无候选索引路径上看似合法。

### 测试契约

#### 先看会坏在哪里

回归测试让 `find` 与 `explain` 在空集合上执行错误 `$in`，并把另一错误操作数藏在逻辑分支后。

??? note "文件差异：tests/test_query.py"
    ```diff
    diff --git a/tests/test_query.py b/tests/test_query.py
    index 9f0a512137586174fa20becbe26c1df9e8c45e42..db527d33859842512c5a15406d77dd4961c4d800 100644
    --- a/tests/test_query.py
    +++ b/tests/test_query.py
    @@ -2,6 +2,7 @@

     import pytest

    +from minimongodb import Collection
     from minimongodb.errors import InvalidQueryError
     from minimongodb.query import matches

    @@ -35,3 +36,20 @@ def test_ne_matches_a_missing_field() -> None:
     def test_unknown_operator_is_rejected() -> None:
         with pytest.raises(InvalidQueryError):
             matches({"age": 20}, {"age": {"$wat": 20}})
    +
    +
    +@pytest.mark.parametrize("method_name", ["find", "explain"])
    +def test_empty_collection_rejects_non_array_in_before_planning(
    +    method_name: str,
    +) -> None:
    +    collection = Collection("empty")
    +
    +    with pytest.raises(InvalidQueryError, match=r"\$in requires an array"):
    +        getattr(collection, method_name)({"x": {"$in": 1}})
    +
    +
    +def test_query_validation_checks_logical_branches_before_matching() -> None:
    +    query = {"$and": [{"x": 1}, {"y": {"$in": 2}}]}
    +
    +    with pytest.raises(InvalidQueryError, match=r"\$in requires an array"):
    +        matches({}, query)
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

回归测试让 `find` 与 `explain` 在空集合上执行错误 `$in`，并把另一错误操作数藏在逻辑分支后。

**关键测试语句**

```python
with pytest.raises(InvalidQueryError, match=r"\$in requires an array"):
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

语法有效性是输入属性，与数据量和访问路径无关，因此校验必须在规划前遍历完整查询树。

### 为什么需要这个机制

若只在匹配文档时校验，非法查询会在空集合或无候选索引路径上看似合法。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Collection 在公共边界统一校验；Matcher 随后按同一套递归检查过的算子契约评估候选。

### 机制板块

#### 规划前的查询校验机制

Collection 在公共边界统一校验；Matcher 随后按同一套递归检查过的算子契约评估候选。

??? note "文件差异：src/minimongodb/query/matcher.py"
    ```diff
    diff --git a/src/minimongodb/query/matcher.py b/src/minimongodb/query/matcher.py
    index e37eb05373517792a5fc6c76e2e9f79e95873230..efad6303400b1874ba1d6030be6a03fd785c815e 100644
    --- a/src/minimongodb/query/matcher.py
    +++ b/src/minimongodb/query/matcher.py
    @@ -14,9 +14,21 @@ from __future__ import annotations
     from collections.abc import Iterable
     from typing import Any

    -from minimongodb.bson import MISSING, bson_compare, bson_equal
    +from minimongodb.bson import bson_compare, bson_equal
     from minimongodb.errors import InvalidQueryError

    +_FIELD_OPERATORS = {
    +    "$eq",
    +    "$gt",
    +    "$gte",
    +    "$lt",
    +    "$lte",
    +    "$ne",
    +    "$in",
    +    "$exists",
    +    "$not",
    +}
    +

     def resolve_path(document: Any, path: str) -> list[Any]:
         """Return every value selected by a dotted path, fanning out through arrays."""
    @@ -26,6 +38,55 @@ def resolve_path(document: Any, path: str) -> list[Any]:
         return _resolve(document, path.split("."))


    +def validate_query(query: Any) -> None:
    +    """Validate the complete supported query grammar without reading a document."""
    +
    +    if not isinstance(query, dict):
    +        raise InvalidQueryError("query must be a document")
    +    for key, condition in query.items():
    +        if not isinstance(key, str):
    +            raise InvalidQueryError("query keys must be strings")
    +        if key in {"$and", "$or"}:
    +            if not isinstance(condition, list):
    +                raise InvalidQueryError(f"{key} requires an array")
    +            for child in condition:
    +                validate_query(child)
    +        elif key == "$not":
    +            if not isinstance(condition, dict):
    +                raise InvalidQueryError("$not requires a query document")
    +            validate_query(condition)
    +        elif key.startswith("$"):
    +            raise InvalidQueryError(f"unsupported logical operator: {key}")
    +        else:
    +            resolve_path({}, key)
    +            _validate_field_condition(condition)
    +
    +
    +def _validate_field_condition(condition: Any) -> None:
    +    if not isinstance(condition, dict):
    +        return
    +    operators = [
    +        key
    +        for key in condition
    +        if isinstance(key, str) and key.startswith("$")
    +    ]
    +    if not operators:
    +        return
    +    if len(operators) != len(condition):
    +        raise InvalidQueryError("cannot mix operators and literal fields")
    +    for operator, operand in condition.items():
    +        if operator not in _FIELD_OPERATORS:
    +            raise InvalidQueryError(f"unsupported query operator: {operator}")
    +        if operator == "$exists" and not isinstance(operand, bool):
    +            raise InvalidQueryError("$exists requires a boolean")
    +        if operator == "$in" and not isinstance(operand, list):
    +            raise InvalidQueryError("$in requires an array")
    +        if operator == "$not":
    +            if not isinstance(operand, dict):
    +                raise InvalidQueryError("$not requires an operator document")
    +            _validate_field_condition(operand)
    +
    +
     def _resolve(current: Any, parts: list[str]) -> list[Any]:
         if not parts:
             return [current]
    @@ -123,8 +184,7 @@ def matches(document: dict[str, Any], query: dict[str, Any] | None = None) -> bo

         if query is None:
             query = {}
    -    if not isinstance(query, dict):
    -        raise InvalidQueryError("query must be a document")
    +    validate_query(query)
         for key, condition in query.items():
             if key == "$and":
                 if not isinstance(condition, list):
    ```

**是什么，为什么现在需要**

语法有效性是输入属性，与数据量和访问路径无关，因此校验必须在规划前遍历完整查询树。

**在运行时做什么**

Collection 在公共边界统一校验；Matcher 随后按同一套递归检查过的算子契约评估候选。

**关键语句理解**

把校验移到选计划之前，可让同一非法查询在空集合、扫描与索引集合上都一致失败。

#### 包、Fixture 与工程支撑

保持包导出、测试语料、依赖与运行环境可复现。

??? note "支撑文件差异（1 个文件）"
    **`src/minimongodb/query/__init__.py`**

    ```diff
    diff --git a/src/minimongodb/query/__init__.py b/src/minimongodb/query/__init__.py
    index 50d90024afacb17c66697886dcad913cc9904af5..500ff043d7320c8a21d2ca881ef01b0d9734a884 100644
    --- a/src/minimongodb/query/__init__.py
    +++ b/src/minimongodb/query/__init__.py
    @@ -1,5 +1,5 @@
     """Mongo-shaped query matching over in-memory teaching documents."""

    -from minimongodb.query.matcher import matches, resolve_path
    +from minimongodb.query.matcher import matches, resolve_path, validate_query

    -__all__ = ["matches", "resolve_path"]
    +__all__ = ["matches", "resolve_path", "validate_query"]
    ```


### 验证证据

运行 `uv run pytest -q $(cat journey/stages/07-query-validation-regression/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

把校验移到选计划之前，可让同一非法查询在空集合、扫描与索引集合上都一致失败。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 3 章](https://github.com/system-in-miniature/mini-mongodb/blob/main/docs/zh/tutorial/03-queries.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-mongodb/blob/main/journey/stages/07-query-validation-regression/stage.patch)
