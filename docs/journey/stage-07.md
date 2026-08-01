# Stage 07 · Query validation before planning

### Goal

Build query validation before planning and explain its boundary from an executable counterexample, runtime state, and the critical statement.

??? note "Deliverable files"
    - `src/minimongodb/query/__init__.py`
    - `src/minimongodb/query/matcher.py`
    - `tests/test_query.py`

### The problem at this point

When validation occurs only while matching documents, an invalid query can appear valid on an empty collection or an index path with no candidate.

### Test contract

#### See the failure first

The regression asks both `find` and `explain` to execute a malformed `$in` against an empty collection and nests another malformed operand behind a logical branch.

??? note "File diff: tests/test_query.py"
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

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The regression asks both `find` and `explain` to execute a malformed `$in` against an empty collection and nests another malformed operand behind a logical branch.

**Key test statement**

```python
with pytest.raises(InvalidQueryError, match=r"\$in requires an array"):
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

Syntax validity is an input property, independent of data cardinality or the chosen access path. Validation therefore walks the complete query tree before planning.

### Why this mechanism is necessary

When validation occurs only while matching documents, an invalid query can appear valid on an empty collection or an index path with no candidate. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

Collection validates once at the public boundary; matcher can then evaluate candidates under the same recursively checked operator contract.

### Mechanism blocks

#### Query validation before planning mechanism

Collection validates once at the public boundary; matcher can then evaluate candidates under the same recursively checked operator contract.

??? note "File diff: src/minimongodb/query/matcher.py"
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

**What it is and why it appears**

Syntax validity is an input property, independent of data cardinality or the chosen access path. Validation therefore walks the complete query tree before planning.

**Runtime role**

Collection validates once at the public boundary; matcher can then evaluate candidates under the same recursively checked operator contract.

**Statement understanding**

Moving validation ahead of plan selection makes the same malformed query fail for empty, scanned, and indexed collections.

#### Package, fixture, and project support

Keep exports, test corpora, dependencies, and the runtime environment reproducible.

??? note "Supporting file diffs (1 file)"
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


### Verification evidence

Run `uv run pytest -q $(cat journey/stages/07-query-validation-regression/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

Moving validation ahead of plan selection makes the same malformed query fail for empty, scanned, and indexed collections.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 3](https://github.com/system-in-miniature/mini-mongodb/blob/main/docs/tutorial/03-queries.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-mongodb/blob/main/journey/stages/07-query-validation-regression/stage.patch)
