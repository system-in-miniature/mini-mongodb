"""Aggregation as a sequence of small document-to-document operators.

Each stage consumes the previous stage's iterable.  Streaming stages
(``$match``, ``$project``, ``$limit``) stay lazy; blocking stages
(``$group``, ``$sort``) materialize exactly where their semantics require it.
That boundary is the document-model counterpart to relational operator trees.
"""

from __future__ import annotations

from copy import deepcopy
from functools import cmp_to_key
from typing import Any, Iterable, Iterator

from minimongodb.bson import (
    MISSING,
    bson_compare,
    canonical_key,
    clone_document,
    get_path,
    set_path,
    unset_path,
)
from minimongodb.errors import InvalidPipelineError
from minimongodb.query import matches

_UNSET = object()


def execute_pipeline(
    documents: Iterable[dict[str, Any]], pipeline: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if not isinstance(pipeline, list):
        raise InvalidPipelineError("pipeline must be an array of stages")
    stream: Iterable[dict[str, Any]] = (
        clone_document(document) for document in documents
    )
    for stage in pipeline:
        if not isinstance(stage, dict) or len(stage) != 1:
            raise InvalidPipelineError("each stage must contain exactly one operator")
        operator, specification = next(iter(stage.items()))
        if operator == "$match":
            if not isinstance(specification, dict):
                raise InvalidPipelineError("$match requires a query document")
            stream = _match(stream, specification)
        elif operator == "$project":
            stream = _project(stream, specification)
        elif operator == "$group":
            stream = _group(stream, specification)
        elif operator == "$sort":
            stream = _sort(stream, specification)
        elif operator == "$limit":
            stream = _limit(stream, specification)
        else:
            raise InvalidPipelineError(f"unsupported pipeline stage: {operator}")
    return list(stream)


def _match(
    documents: Iterable[dict[str, Any]], query: dict[str, Any]
) -> Iterator[dict[str, Any]]:
    for document in documents:
        if matches(document, query):
            yield document


def _project(
    documents: Iterable[dict[str, Any]], specification: Any
) -> Iterator[dict[str, Any]]:
    if not isinstance(specification, dict) or not specification:
        raise InvalidPipelineError("$project requires a non-empty document")
    excluded = {
        field for field, expression in specification.items() if expression in (0, False)
    }
    included = set(specification) - excluded
    if excluded - {"_id"} and included:
        raise InvalidPipelineError(
            "$project cannot mix exclusion with inclusion or computed fields"
        )

    for document in documents:
        if included:
            projected: dict[str, Any] = {}
            if specification.get("_id", 1) not in (0, False) and "_id" in document:
                projected["_id"] = deepcopy(document["_id"])
            for field in included - {"_id"}:
                expression = specification[field]
                value = (
                    get_path(document, field)
                    if expression in (1, True)
                    else _evaluate(document, expression)
                )
                if value is not MISSING:
                    set_path(projected, field, deepcopy(value))
            yield projected
        else:
            projected = clone_document(document)
            for field in excluded:
                unset_path(projected, field)
            yield projected


def _group(
    documents: Iterable[dict[str, Any]], specification: Any
) -> Iterable[dict[str, Any]]:
    if not isinstance(specification, dict) or "_id" not in specification:
        raise InvalidPipelineError("$group requires an _id expression")
    accumulator_specs: dict[str, tuple[str, Any]] = {}
    for output, accumulator in specification.items():
        if output == "_id":
            continue
        if not isinstance(accumulator, dict) or len(accumulator) != 1:
            raise InvalidPipelineError("group fields require one accumulator")
        operator, expression = next(iter(accumulator.items()))
        if operator not in {"$sum", "$avg", "$min", "$max", "$push"}:
            raise InvalidPipelineError(f"unsupported group accumulator: {operator}")
        accumulator_specs[output] = (operator, expression)

    groups: dict[tuple[Any, ...], dict[str, Any]] = {}
    averages: dict[tuple[Any, ...], dict[str, tuple[float, int]]] = {}
    for document in documents:
        group_value = _evaluate(document, specification["_id"])
        if group_value is MISSING:
            group_value = None
        group_key = canonical_key(group_value)
        if group_key not in groups:
            groups[group_key] = {"_id": deepcopy(group_value)}
            averages[group_key] = {}
            for output, (operator, _expression) in accumulator_specs.items():
                if operator == "$push":
                    groups[group_key][output] = []
                elif operator in {"$min", "$max"}:
                    groups[group_key][output] = _UNSET
                else:
                    groups[group_key][output] = None

        result = groups[group_key]
        for output, (operator, expression) in accumulator_specs.items():
            value = _evaluate(document, expression)
            if operator == "$push":
                result[output].append(None if value is MISSING else deepcopy(value))
            elif operator == "$sum":
                numeric = _numeric(value)
                result[output] = (result[output] or 0) + (numeric or 0)
            elif operator == "$avg":
                numeric = _numeric(value)
                if numeric is not None:
                    total, count = averages[group_key].get(output, (0.0, 0))
                    averages[group_key][output] = (total + numeric, count + 1)
            elif value is not MISSING:
                current = result[output]
                if current is _UNSET:
                    result[output] = deepcopy(value)
                else:
                    compared = bson_compare(value, current)
                    if (operator == "$min" and compared < 0) or (
                        operator == "$max" and compared > 0
                    ):
                        result[output] = deepcopy(value)

    for group_key, result in groups.items():
        for output, (operator, _expression) in accumulator_specs.items():
            if operator == "$avg":
                aggregate = averages[group_key].get(output)
                result[output] = (
                    aggregate[0] / aggregate[1] if aggregate is not None else None
                )
            elif operator == "$sum" and result[output] is None:
                result[output] = 0
            elif operator in {"$min", "$max"} and result[output] is _UNSET:
                result[output] = None
    return groups.values()


def _sort(
    documents: Iterable[dict[str, Any]], specification: Any
) -> Iterable[dict[str, Any]]:
    if not isinstance(specification, dict) or not specification:
        raise InvalidPipelineError("$sort requires a non-empty key pattern")
    if any(direction not in (1, -1) for direction in specification.values()):
        raise InvalidPipelineError("$sort directions must be 1 or -1")

    def compare(left: dict[str, Any], right: dict[str, Any]) -> int:
        for field, direction in specification.items():
            left_value = get_path(left, field)
            right_value = get_path(right, field)
            if left_value is MISSING:
                left_value = None
            if right_value is MISSING:
                right_value = None
            compared = bson_compare(left_value, right_value)
            if compared:
                return compared * direction
        return 0

    return sorted(documents, key=cmp_to_key(compare))


def _limit(
    documents: Iterable[dict[str, Any]], specification: Any
) -> Iterator[dict[str, Any]]:
    if (
        isinstance(specification, bool)
        or not isinstance(specification, int)
        or specification < 0
    ):
        raise InvalidPipelineError("$limit requires a non-negative integer")
    for position, document in enumerate(documents):
        if position >= specification:
            break
        yield document


def _evaluate(document: dict[str, Any], expression: Any) -> Any:
    if isinstance(expression, str) and expression.startswith("$"):
        if expression == "$":
            return document
        return get_path(document, expression[1:])
    if isinstance(expression, dict):
        evaluated: dict[str, Any] = {}
        for key, child in expression.items():
            value = _evaluate(document, child)
            if value is not MISSING:
                evaluated[key] = value
        return evaluated
    if isinstance(expression, list):
        return [
            None if (value := _evaluate(document, child)) is MISSING else value
            for child in expression
        ]
    return deepcopy(expression)


def _numeric(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


__all__ = ["execute_pipeline"]
