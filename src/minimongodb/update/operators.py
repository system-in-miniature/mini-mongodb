"""Apply M1 update operators to an isolated document copy.

Collection code clones a stored document first, invokes this module, validates
the result, and only then swaps it into storage.  That order is the miniature
version of atomic single-document updates: a failing second operator cannot
leave the first operator half-applied.
"""

from __future__ import annotations

from numbers import Real
from typing import Any

from minimongodb.bson import (
    MISSING,
    bson_equal,
    clone_document,
    get_path,
    set_path,
    unset_path,
)
from minimongodb.errors import ImmutableIdError, InvalidUpdateError, PathError
from minimongodb.query import matches

SUPPORTED_OPERATORS = {"$set", "$unset", "$inc", "$push", "$pull"}


def _guards_id(path: str) -> None:
    if path == "_id" or path.startswith("_id."):
        raise ImmutableIdError("_id is immutable")


def _mapping_operand(operator: str, operand: Any) -> dict[str, Any]:
    if not isinstance(operand, dict):
        raise InvalidUpdateError(f"{operator} requires a document operand")
    return operand


def apply_operator_update(
    original: dict[str, Any], update: dict[str, Any]
) -> dict[str, Any]:
    """Return an updated copy, never mutating the stored original."""

    if not update or not all(key.startswith("$") for key in update):
        raise InvalidUpdateError("operator update must contain only $ operators")
    unknown = set(update) - SUPPORTED_OPERATORS
    if unknown:
        raise InvalidUpdateError(f"unsupported update operator: {sorted(unknown)[0]}")

    document = clone_document(original)
    try:
        for operator, raw_operand in update.items():
            operand = _mapping_operand(operator, raw_operand)
            for path, value in operand.items():
                _guards_id(path)
                if operator == "$set":
                    set_path(document, path, value)
                elif operator == "$unset":
                    unset_path(document, path)
                elif operator == "$inc":
                    current = get_path(document, path)
                    if isinstance(value, bool) or not isinstance(value, Real):
                        raise InvalidUpdateError("$inc amount must be numeric")
                    if current is MISSING:
                        set_path(document, path, value)
                    elif isinstance(current, bool) or not isinstance(current, Real):
                        raise InvalidUpdateError("$inc target must be numeric")
                    else:
                        set_path(document, path, current + value)
                elif operator == "$push":
                    current = get_path(document, path)
                    if current is MISSING:
                        set_path(document, path, [value])
                    elif not isinstance(current, list):
                        raise InvalidUpdateError("$push target must be an array")
                    else:
                        current.append(value)
                elif operator == "$pull":
                    current = get_path(document, path)
                    if current is MISSING:
                        continue
                    if not isinstance(current, list):
                        raise InvalidUpdateError("$pull target must be an array")
                    current[:] = [
                        item for item in current if not matches({"value": item}, {"value": value})
                    ]
    except PathError as error:
        raise InvalidUpdateError(str(error)) from error
    # Values in the user's update document may themselves be mutable.  The
    # second boundary copy both validates those newly introduced values and
    # prevents later caller mutations from changing stored state.
    return clone_document(document)


def replacement_document(
    original: dict[str, Any], replacement: dict[str, Any]
) -> dict[str, Any]:
    """Build a replacement while preserving an omitted immutable ``_id``."""

    if not isinstance(replacement, dict):
        raise InvalidUpdateError("replacement must be a document")
    if any(key.startswith("$") for key in replacement):
        raise InvalidUpdateError("replacement cannot contain top-level operators")
    result = clone_document(replacement)
    old_id = original["_id"]
    if "_id" in result and not bson_equal(result["_id"], old_id):
        raise ImmutableIdError("_id is immutable")
    if "_id" not in result:
        result["_id"] = old_id
    return result
