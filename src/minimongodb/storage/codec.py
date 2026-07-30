"""Deterministic tagged JSON codec for the supported BSON teaching subset.

Using tagged nodes avoids silently turning an ``ObjectId`` into a string or a
boolean into a number.  Real MongoDB writes binary BSON/WiredTiger pages; JSON
here is an inspectable serialization detail, not a claim of wire compatibility.
"""

from __future__ import annotations

import json
from typing import Any

from minimongodb.bson import ObjectId, type_tag
from minimongodb.oplog import OplogEntry


def _to_node(value: Any) -> dict[str, Any]:
    tag = type_tag(value)
    if tag == "document":
        return {"t": "document", "v": [[key, _to_node(item)] for key, item in value.items()]}
    if tag == "array":
        return {"t": "array", "v": [_to_node(item) for item in value]}
    if tag == "objectId":
        return {"t": "objectId", "v": value.value}
    return {"t": tag, "v": value}


def _from_node(node: dict[str, Any]) -> Any:
    tag = node["t"]
    value = node["v"]
    if tag == "document":
        return {key: _from_node(item) for key, item in value}
    if tag == "array":
        return [_from_node(item) for item in value]
    if tag == "objectId":
        return ObjectId(value)
    if tag in {"null", "number", "string", "bool"}:
        return value
    raise ValueError(f"unknown encoded type tag: {tag!r}")


def encode_value(value: Any) -> bytes:
    """Encode one supported value with stable separators and key ordering."""

    return json.dumps(
        _to_node(value),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def decode_value(payload: bytes) -> Any:
    return _from_node(json.loads(payload.decode("utf-8")))


def encode_entry(entry: OplogEntry) -> bytes:
    return encode_value(
        {
            "sequence": entry.sequence,
            "collection": entry.collection,
            "operation": entry.operation,
            "key": entry.key,
            "payload": entry.payload,
        }
    )


def decode_entry(payload: bytes) -> OplogEntry:
    value = decode_value(payload)
    return OplogEntry(
        value["sequence"],
        value["collection"],
        value["operation"],
        value["key"],
        value["payload"],
    )
