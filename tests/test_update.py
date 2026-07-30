"""Update routing, dotted operators, and immutable identity."""

import pytest

from minimongodb import Collection
from minimongodb.errors import ImmutableIdError, InvalidUpdateError


def test_set_unset_and_inc_follow_dotted_paths() -> None:
    collection = Collection()
    collection.insert_one({"_id": 1, "stats": {"count": 2}, "old": True})
    result = collection.update_one(
        {"_id": 1},
        {"$set": {"stats.label": "ok"}, "$inc": {"stats.count": 3}, "$unset": {"old": ""}},
    )
    assert (result.matched_count, result.modified_count) == (1, 1)
    assert collection.find_one({"_id": 1}) == {
        "_id": 1,
        "stats": {"count": 5, "label": "ok"},
    }


def test_push_and_pull_use_array_element_matching() -> None:
    collection = Collection()
    collection.insert_one({"_id": 1, "tags": ["db"], "scores": [2, 8, 3]})
    collection.update_one(
        {"_id": 1},
        {"$push": {"tags": "python"}, "$pull": {"scores": {"$gt": 5}}},
    )
    assert collection.find_one({"_id": 1}) == {
        "_id": 1,
        "tags": ["db", "python"],
        "scores": [2, 3],
    }


def test_update_many_counts_matches_and_actual_modifications() -> None:
    collection = Collection()
    collection.insert_many([{"_id": 1, "x": 1}, {"_id": 2, "x": 1}])
    result = collection.update_many({"x": 1}, {"$set": {"x": 1}})
    assert (result.matched_count, result.modified_count) == (2, 0)


def test_replace_document_preserves_id_when_omitted() -> None:
    collection = Collection()
    collection.insert_one({"_id": 1, "old": True})
    result = collection.replace_one({"_id": 1}, {"new": True})
    assert (result.matched_count, result.modified_count) == (1, 1)
    assert collection.find_one() == {"new": True, "_id": 1}


@pytest.mark.parametrize(
    "operation",
    [
        lambda c: c.update_one({"_id": 1}, {"$set": {"_id": 2}}),
        lambda c: c.update_one({"_id": 1}, {"$unset": {"_id": ""}}),
        lambda c: c.replace_one({"_id": 1}, {"_id": 2}),
    ],
)
def test_id_is_immutable(operation) -> None:
    collection = Collection()
    collection.insert_one({"_id": 1})
    with pytest.raises(ImmutableIdError):
        operation(collection)


def test_operator_and_replacement_syntax_cannot_be_mixed() -> None:
    collection = Collection()
    collection.insert_one({"_id": 1})
    with pytest.raises(InvalidUpdateError):
        collection.update_one({"_id": 1}, {"$set": {"x": 1}, "plain": 2})


def test_update_values_are_validated_and_copied_before_storage() -> None:
    collection = Collection()
    collection.insert_one({"_id": 1, "items": []})
    caller_owned = {"nested": [1]}
    collection.update_one({"_id": 1}, {"$set": {"value": caller_owned}})
    caller_owned["nested"].append(2)
    assert collection.find_one({"_id": 1})["value"] == {"nested": [1]}

    with pytest.raises(TypeError, match="unsupported BSON value"):
        collection.update_one({"_id": 1}, {"$push": {"items": {1, 2}}})
    assert collection.find_one({"_id": 1})["items"] == []
