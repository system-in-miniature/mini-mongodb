"""Deterministic COLLSCAN/IXSCAN planning with observable execution counts.

The estimate is intentionally small: each prefix-compatible index reports the
number of candidate documents for the query bounds.  An IXSCAN wins only when
it examines fewer documents than a collection scan, with deterministic ties by
candidate count, longer compound prefix, then index name.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from minimongodb.bson import canonical_key
from minimongodb.index import IdIndex, SecondaryIndex


@dataclass(frozen=True, slots=True)
class Plan:
    stage: str
    index: SecondaryIndex | None = None
    prefix_length: int = 0
    candidate_ids: set[tuple[Any, ...]] | None = None
    keys_examined: int = 0
    summary_override: dict[str, Any] | None = None

    def summary(self, query: dict[str, Any]) -> dict[str, Any]:
        if self.summary_override is not None:
            return self.summary_override
        if self.index is None:
            return {"stage": "COLLSCAN"}
        fields = [field for field, _direction in self.index.spec[: self.prefix_length]]
        return {
            "stage": "IXSCAN",
            "indexName": self.index.name,
            "keyPattern": self.index.key_pattern,
            "indexBounds": {field: query[field] for field in fields},
        }


def choose_plan(
    query: dict[str, Any],
    document_count: int,
    indexes: Iterable[SecondaryIndex],
    id_index: IdIndex | None = None,
) -> Plan:
    id_values = _id_lookup_values(query)
    if (
        id_index is not None
        and id_index.has_root_array
        and not _id_lookup_is_safe_with_array_ids(query)
    ):
        id_values = None
    if id_index is not None and id_values is not None:
        candidate_ids = {
            canonical_key(document["_id"])
            for value in id_values
            if (document := id_index.get(value)) is not None
        }
        return Plan(
            "IXSCAN",
            candidate_ids=candidate_ids,
            keys_examined=len(id_values),
            summary_override={
                "stage": "IXSCAN",
                "indexName": "_id_",
                "keyPattern": {"_id": 1},
                "indexBounds": {"_id": query["_id"]},
            },
        )
    candidates: list[tuple[int, int, str, SecondaryIndex, set, int]] = []
    for index in indexes:
        prefix_length = index.prefix_length(query)
        if not prefix_length:
            continue
        document_ids, keys_examined = index.scan(query, prefix_length)
        candidates.append(
            (
                len(document_ids),
                -prefix_length,
                index.name,
                index,
                document_ids,
                keys_examined,
            )
        )
    if not candidates:
        return Plan("COLLSCAN")
    estimate, negative_prefix, _name, index, document_ids, keys_examined = min(
        candidates, key=lambda candidate: candidate[:3]
    )
    if estimate >= document_count:
        return Plan("COLLSCAN")
    return Plan(
        "IXSCAN",
        index=index,
        prefix_length=-negative_prefix,
        candidate_ids=document_ids,
        keys_examined=keys_examined,
    )


def _id_lookup_values(query: dict[str, Any]) -> list[Any] | None:
    if "_id" not in query:
        return None
    condition = query["_id"]
    if isinstance(condition, dict) and any(
        isinstance(key, str) and key.startswith("$") for key in condition
    ):
        if set(condition) == {"$eq"}:
            return [condition["$eq"]]
        if set(condition) == {"$in"} and isinstance(condition["$in"], list):
            return condition["$in"]
        return None
    return [condition]


def _id_lookup_is_safe_with_array_ids(query: dict[str, Any]) -> bool:
    if "_id" not in query:
        return True
    condition = query["_id"]
    if isinstance(condition, dict) and any(
        isinstance(key, str) and key.startswith("$") for key in condition
    ):
        if set(condition) == {"$eq"}:
            return isinstance(condition["$eq"], (dict, list))
        if set(condition) == {"$in"} and isinstance(condition["$in"], list):
            return all(
                isinstance(option, (dict, list)) for option in condition["$in"]
            )
        return False
    return isinstance(condition, (dict, list))


__all__ = ["Plan", "choose_plan"]
