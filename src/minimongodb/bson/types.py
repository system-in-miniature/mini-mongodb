"""A JSON-shaped BSON value model with explicit teaching-only type ordering.

Real BSON is a binary format with more types and a different comparison order.
MiniMongoDB stores ordinary Python dictionaries/lists and adds only an
``ObjectId`` analogue.  The deliberately small cross-type order is:

``null < number < string < document < array < bool < objectId``.

Notably, Python's ``bool`` is kept out of ``number`` even though ``bool`` is an
``int`` subclass.  Comparisons recurse deterministically through documents in
insertion order and arrays by element, which is useful for teaching but is not
a byte-for-byte reproduction of MongoDB's BSON comparator.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from functools import total_ordering
from itertools import count
from math import isnan
from typing import Any


@total_ordering
@dataclass(frozen=True, slots=True)
class ObjectId:
    """Deterministic ObjectId analogue backed by a non-negative counter."""

    value: int

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int):
            raise TypeError("ObjectId value must be an integer")
        if not 0 <= self.value < 2**96:
            raise ValueError("ObjectId value must fit in 12 bytes")

    def __str__(self) -> str:
        return f"{self.value:024x}"

    def __repr__(self) -> str:
        return f"ObjectId('{self}')"

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, ObjectId):
            return NotImplemented
        return self.value < other.value


class CounterObjectIdGenerator:
    """Callable ID source; injection makes every test and lab reproducible."""

    def __init__(self, start: int = 1) -> None:
        self._counter = count(start)

    def __call__(self) -> ObjectId:
        return ObjectId(next(self._counter))


_TYPE_ORDER = {
    "null": 0,
    "number": 1,
    "string": 2,
    "document": 3,
    "array": 4,
    "bool": 5,
    "objectId": 6,
}


def type_tag(value: Any) -> str:
    """Return the supported BSON-like tag or reject an ambiguous value."""

    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("document keys must be strings")
        return "document"
    if isinstance(value, list):
        return "array"
    if isinstance(value, ObjectId):
        return "objectId"
    raise TypeError(f"unsupported BSON value: {type(value).__name__}")


def clone_document(document: dict[str, Any]) -> dict[str, Any]:
    """Copy at the API boundary so callers cannot mutate stored state."""

    if type_tag(document) != "document":
        raise TypeError("a document must be a dict with string keys")
    _validate_tree(document)
    # deepcopy is safe because the supported graph contains only value objects.
    return deepcopy(document)


def _validate_tree(value: Any) -> None:
    """Validate every nested node before it can cross the storage boundary."""

    tag = type_tag(value)
    if tag == "document":
        for child in value.values():
            _validate_tree(child)
    elif tag == "array":
        for child in value:
            _validate_tree(child)


def bson_equal(left: Any, right: Any) -> bool:
    """Exact value equality; document field order is significant like BSON."""

    try:
        if type_tag(left) != type_tag(right):
            # BSON numeric values compare by numeric value across int/float.
            return False
    except TypeError:
        return False
    if isinstance(left, float) and isnan(left):
        return isinstance(right, float) and isnan(right)
    if isinstance(left, dict):
        return list(left.keys()) == list(right.keys()) and all(
            bson_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            bson_equal(a, b) for a, b in zip(left, right)
        )
    return left == right


def bson_compare(left: Any, right: Any) -> int:
    """Three-way comparison using MiniMongoDB's documented type order."""

    left_tag = type_tag(left)
    right_tag = type_tag(right)
    if left_tag != right_tag:
        return (_TYPE_ORDER[left_tag] > _TYPE_ORDER[right_tag]) - (
            _TYPE_ORDER[left_tag] < _TYPE_ORDER[right_tag]
        )
    if bson_equal(left, right):
        return 0
    if left_tag == "document":
        left_items = list(left.items())
        right_items = list(right.items())
        for (left_key, left_value), (right_key, right_value) in zip(
            left_items, right_items
        ):
            if left_key != right_key:
                return (left_key > right_key) - (left_key < right_key)
            compared = bson_compare(left_value, right_value)
            if compared:
                return compared
        return (len(left_items) > len(right_items)) - (
            len(left_items) < len(right_items)
        )
    if left_tag == "array":
        for left_value, right_value in zip(left, right):
            compared = bson_compare(left_value, right_value)
            if compared:
                return compared
        return (len(left) > len(right)) - (len(left) < len(right))
    return (left > right) - (left < right)
