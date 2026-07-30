"""Query operator contract independent of collection storage."""

import pytest

from minimongodb import Collection
from minimongodb.errors import InvalidQueryError
from minimongodb.query import matches


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ({"age": 20}, True),
        ({"age": {"$eq": 20}}, True),
        ({"age": {"$gt": 19, "$lte": 20}}, True),
        ({"age": {"$gte": 20, "$lt": 21}}, True),
        ({"age": {"$ne": 21}}, True),
        ({"age": {"$in": [10, 20]}}, True),
        ({"missing": {"$exists": False}}, True),
        ({"age": {"$exists": True}}, True),
        ({"$and": [{"age": 20}, {"name": "Ada"}]}, True),
        ({"$or": [{"age": 99}, {"name": "Ada"}]}, True),
        ({"age": {"$not": {"$gt": 20}}}, True),
        ({"$not": {"name": "Grace"}}, True),
        ({"age": {"$lt": 20}}, False),
    ],
)
def test_query_operators(query: dict, expected: bool) -> None:
    assert matches({"name": "Ada", "age": 20}, query) is expected


def test_ne_matches_a_missing_field() -> None:
    assert matches({}, {"age": {"$ne": 20}})


def test_unknown_operator_is_rejected() -> None:
    with pytest.raises(InvalidQueryError):
        matches({"age": 20}, {"age": {"$wat": 20}})


@pytest.mark.parametrize("method_name", ["find", "explain"])
def test_empty_collection_rejects_non_array_in_before_planning(
    method_name: str,
) -> None:
    collection = Collection("empty")

    with pytest.raises(InvalidQueryError, match=r"\$in requires an array"):
        getattr(collection, method_name)({"x": {"$in": 1}})


def test_query_validation_checks_logical_branches_before_matching() -> None:
    query = {"$and": [{"x": 1}, {"y": {"$in": 2}}]}

    with pytest.raises(InvalidQueryError, match=r"\$in requires an array"):
        matches({}, query)
