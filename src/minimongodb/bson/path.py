"""Dotted-path primitives shared by querying and updating.

Numeric segments address list elements (``items.0.name``).  Writers create
missing dictionary containers, but never guess how large an array should be;
that explicit restriction prevents surprising sparse-list behavior.
"""

from __future__ import annotations

from typing import Any

from minimongodb.errors import PathError


class _Missing:
    def __repr__(self) -> str:
        return "MISSING"


MISSING = _Missing()


def _parts(path: str) -> list[str]:
    if not isinstance(path, str) or not path or any(not part for part in path.split(".")):
        raise PathError("path must contain non-empty dot-separated segments")
    return path.split(".")


def get_path(document: Any, path: str) -> Any:
    """Read one exact path; query fan-out over arrays lives in ``query``."""

    current = document
    for part in _parts(path):
        if isinstance(current, dict):
            if part not in current:
                return MISSING
            current = current[part]
        elif isinstance(current, list):
            if not part.isdigit():
                return MISSING
            index = int(part)
            if index >= len(current):
                return MISSING
            current = current[index]
        else:
            return MISSING
    return current


def set_path(document: dict[str, Any], path: str, value: Any) -> None:
    """Set a path, creating only unambiguous missing dictionary containers."""

    parts = _parts(path)
    current: Any = document
    for index, part in enumerate(parts[:-1]):
        next_part = parts[index + 1]
        if isinstance(current, dict):
            if part not in current:
                # A numeric next segment signals an array, but inventing its
                # length would be ambiguous, so only dictionaries are created.
                if next_part.isdigit():
                    raise PathError("cannot create a missing array implicitly")
                current[part] = {}
            current = current[part]
        elif isinstance(current, list):
            if not part.isdigit():
                raise PathError(f"list segment must be numeric: {part!r}")
            position = int(part)
            if position >= len(current):
                raise PathError("array index is out of range")
            current = current[position]
        else:
            raise PathError(f"cannot traverse scalar at segment {part!r}")

    final = parts[-1]
    if isinstance(current, dict):
        current[final] = value
    elif isinstance(current, list):
        if not final.isdigit():
            raise PathError(f"list segment must be numeric: {final!r}")
        position = int(final)
        if position >= len(current):
            raise PathError("array index is out of range")
        current[position] = value
    else:
        raise PathError("cannot set a child of a scalar")


def unset_path(document: dict[str, Any], path: str) -> bool:
    """Remove a mapping key; array positions become ``None`` rather than shift."""

    parts = _parts(path)
    parent = get_path(document, ".".join(parts[:-1])) if len(parts) > 1 else document
    if parent is MISSING:
        return False
    final = parts[-1]
    if isinstance(parent, dict):
        return parent.pop(final, MISSING) is not MISSING
    if isinstance(parent, list) and final.isdigit():
        position = int(final)
        if position < len(parent):
            # MongoDB's $unset on an array index preserves indices with null.
            parent[position] = None
            return True
    return False
