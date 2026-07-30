"""Query matcher with deliberate separation of path fan-out and equality.

The crucial distinction is easy to lose in one clever recursive function:

* traversing a dotted path may fan out through an array of documents;
* comparing a scalar to an array may inspect each array element;
* comparing a literal document or array remains exact whole-value equality.

Keeping these steps separate makes the MongoDB-specific behavior visible.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from minimongodb.bson import MISSING, bson_compare, bson_equal
from minimongodb.errors import InvalidQueryError


def resolve_path(document: Any, path: str) -> list[Any]:
    """Return every value selected by a dotted path, fanning out through arrays."""

    if not isinstance(path, str) or not path or any(not p for p in path.split(".")):
        raise InvalidQueryError("field path must have non-empty segments")
    return _resolve(document, path.split("."))


def _resolve(current: Any, parts: list[str]) -> list[Any]:
    if not parts:
        return [current]
    part, rest = parts[0], parts[1:]
    if isinstance(current, dict):
        if part not in current:
            return []
        return _resolve(current[part], rest)
    if isinstance(current, list):
        if part.isdigit():
            position = int(part)
            return _resolve(current[position], rest) if position < len(current) else []
        # Do not consume the part: each element must still resolve that field.
        return [
            value
            for element in current
            for value in _resolve(element, parts)
        ]
    return []


def _array_candidates(value: Any, expected: Any) -> Iterable[Any]:
    """Expand stored arrays only when the query operand is scalar-like."""

    if isinstance(value, list) and not isinstance(expected, (list, dict)):
        for item in value:
            # Nested arrays also expose scalar leaves for this teaching subset.
            yield from _array_candidates(item, expected)
    else:
        yield value


def _equals(value: Any, expected: Any) -> bool:
    return any(bson_equal(candidate, expected) for candidate in _array_candidates(value, expected))


def _compare(value: Any, expected: Any, operator: str) -> bool:
    def accepted(candidate: Any) -> bool:
        compared = bson_compare(candidate, expected)
        return {
            "$gt": compared > 0,
            "$gte": compared >= 0,
            "$lt": compared < 0,
            "$lte": compared <= 0,
        }[operator]

    try:
        return any(accepted(candidate) for candidate in _array_candidates(value, expected))
    except TypeError:
        return False


def _operator_matches(values: list[Any], operator: str, operand: Any) -> bool:
    present = bool(values)
    if operator == "$exists":
        if not isinstance(operand, bool):
            raise InvalidQueryError("$exists requires a boolean")
        return present is operand
    if operator == "$ne":
        return not any(_equals(value, operand) for value in values)
    if operator == "$not":
        if not isinstance(operand, dict):
            raise InvalidQueryError("$not requires an operator document")
        return not _field_matches(values, operand)
    if not present:
        return False
    if operator == "$eq":
        return any(_equals(value, operand) for value in values)
    if operator in {"$gt", "$gte", "$lt", "$lte"}:
        return any(_compare(value, operand, operator) for value in values)
    if operator == "$in":
        if not isinstance(operand, list):
            raise InvalidQueryError("$in requires an array")
        return any(
            _equals(value, option) for value in values for option in operand
        )
    raise InvalidQueryError(f"unsupported query operator: {operator}")


def _field_matches(values: list[Any], condition: Any) -> bool:
    if isinstance(condition, dict) and any(
        isinstance(key, str) and key.startswith("$") for key in condition
    ):
        if not all(isinstance(key, str) and key.startswith("$") for key in condition):
            raise InvalidQueryError("cannot mix operators and literal fields")
        return all(
            _operator_matches(values, operator, operand)
            for operator, operand in condition.items()
        )
    return bool(values) and any(_equals(value, condition) for value in values)


def matches(document: dict[str, Any], query: dict[str, Any] | None = None) -> bool:
    """Return whether a document satisfies the supported Mongo-shaped query."""

    if query is None:
        query = {}
    if not isinstance(query, dict):
        raise InvalidQueryError("query must be a document")
    for key, condition in query.items():
        if key == "$and":
            if not isinstance(condition, list):
                raise InvalidQueryError("$and requires an array")
            if not all(matches(document, child) for child in condition):
                return False
        elif key == "$or":
            if not isinstance(condition, list):
                raise InvalidQueryError("$or requires an array")
            if not any(matches(document, child) for child in condition):
                return False
        elif key == "$not":
            if not isinstance(condition, dict):
                raise InvalidQueryError("$not requires a query document")
            if matches(document, condition):
                return False
        elif key.startswith("$"):
            raise InvalidQueryError(f"unsupported logical operator: {key}")
        elif not _field_matches(resolve_path(document, key), condition):
            return False
    return True
