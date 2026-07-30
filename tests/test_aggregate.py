"""Aggregation stages compose as a deterministic document operator pipeline."""

import pytest

from minimongodb import Collection
from minimongodb.errors import InvalidPipelineError


def test_match_project_sort_and_limit_pipeline() -> None:
    collection = Collection("sales")
    collection.insert_many(
        [
            {"_id": 1, "region": "west", "item": {"name": "pen"}, "amount": 3},
            {"_id": 2, "region": "east", "item": {"name": "book"}, "amount": 9},
            {"_id": 3, "region": "west", "item": {"name": "book"}, "amount": 7},
        ]
    )

    assert collection.aggregate(
        [
            {"$match": {"region": "west"}},
            {"$project": {"_id": 0, "name": "$item.name", "amount": 1}},
            {"$sort": {"amount": -1}},
            {"$limit": 1},
        ]
    ) == [{"name": "book", "amount": 7}]


def test_group_supports_all_minimum_accumulators() -> None:
    collection = Collection("sales")
    collection.insert_many(
        [
            {"_id": 1, "region": "west", "amount": 3},
            {"_id": 2, "region": "east", "amount": 9},
            {"_id": 3, "region": "west", "amount": 7},
        ]
    )

    assert collection.aggregate(
        [
            {
                "$group": {
                    "_id": "$region",
                    "count": {"$sum": 1},
                    "total": {"$sum": "$amount"},
                    "average": {"$avg": "$amount"},
                    "minimum": {"$min": "$amount"},
                    "maximum": {"$max": "$amount"},
                    "amounts": {"$push": "$amount"},
                }
            },
            {"$sort": {"_id": 1}},
        ]
    ) == [
        {
            "_id": "east",
            "count": 1,
            "total": 9,
            "average": 9.0,
            "minimum": 9,
            "maximum": 9,
            "amounts": [9],
        },
        {
            "_id": "west",
            "count": 2,
            "total": 10,
            "average": 5.0,
            "minimum": 3,
            "maximum": 7,
            "amounts": [3, 7],
        },
    ]


def test_group_min_keeps_null_as_a_real_bson_value() -> None:
    collection = Collection("values")
    collection.insert_many([{"_id": 1, "x": None}, {"_id": 2, "x": 3}])
    assert collection.aggregate(
        [
            {
                "$group": {
                    "_id": None,
                    "minimum": {"$min": "$x"},
                    "maximum": {"$max": "$x"},
                }
            }
        ]
    ) == [{"_id": None, "minimum": None, "maximum": 3}]


def test_project_nested_expression_does_not_leak_missing_sentinel() -> None:
    collection = Collection("values")
    collection.insert_one({"_id": 1})
    assert collection.aggregate(
        [{"$project": {"_id": 0, "object": {"value": "$missing"}}}]
    ) == [{"object": {}}]


@pytest.mark.parametrize(
    "pipeline",
    [
        [{"$unknown": {}}],
        [{"$match": {}, "$limit": 1}],
        [{"$limit": -1}],
        [{"$group": {"_id": "$x", "bad": {"$median": "$x"}}}],
    ],
)
def test_invalid_pipeline_stages_are_rejected(pipeline: list[dict]) -> None:
    with pytest.raises(InvalidPipelineError):
        Collection().aggregate(pipeline)
