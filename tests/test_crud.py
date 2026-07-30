"""Public CRUD contract and automatic unique ``_id`` index."""

from math import nan

import pytest

from minimongodb import Collection, CounterObjectIdGenerator, ObjectId
from minimongodb.errors import DuplicateKeyError


def test_insert_find_and_copy_isolation() -> None:
    collection = Collection("people", id_generator=CounterObjectIdGenerator(10))
    source = {"name": "Ada", "profile": {"city": "London"}}
    result = collection.insert_one(source)

    assert result.inserted_id == ObjectId(10)
    assert "_id" not in source
    found = collection.find({"name": "Ada"})
    assert found == [
        {"name": "Ada", "profile": {"city": "London"}, "_id": ObjectId(10)}
    ]
    found[0]["profile"]["city"] = "changed outside"
    assert collection.find_one({"_id": ObjectId(10)})["profile"]["city"] == "London"


def test_insert_many_uses_counter_in_input_order() -> None:
    collection = Collection(id_generator=CounterObjectIdGenerator(1))
    result = collection.insert_many([{"n": 1}, {"n": 2}])
    assert result.inserted_ids == [ObjectId(1), ObjectId(2)]


def test_id_index_rejects_duplicate_key_without_partial_insert_many() -> None:
    collection = Collection()
    collection.insert_one({"_id": "same", "n": 1})
    with pytest.raises(DuplicateKeyError):
        collection.insert_many([{"_id": "new"}, {"_id": "same"}])
    assert collection.find({}) == [{"_id": "same", "n": 1}]


def test_id_index_keeps_bool_distinct_from_numeric_ids() -> None:
    collection = Collection()
    collection.insert_many([{"_id": True}, {"_id": 1}])
    assert collection.find() == [{"_id": True}, {"_id": 1}]


def test_id_index_uses_bson_numeric_equality_across_int_and_float() -> None:
    collection = Collection()
    collection.insert_one({"_id": 1})
    with pytest.raises(DuplicateKeyError):
        collection.insert_one({"_id": 1.0})

    boundary = Collection()
    boundary.insert_many([{"_id": 2**53 + 1}, {"_id": float(2**53 + 1)}])
    assert len(boundary.find()) == 2


def test_id_index_canonicalizes_nan_and_nested_bson_values() -> None:
    nan_ids = Collection()
    nan_ids.insert_one({"_id": nan})
    with pytest.raises(DuplicateKeyError):
        nan_ids.insert_one({"_id": nan})

    nested_ids = Collection()
    nested_ids.insert_one({"_id": {"a": [True, 1], "b": 2}})
    with pytest.raises(DuplicateKeyError):
        nested_ids.insert_one({"_id": {"a": [True, 1], "b": 2.0}})
    nested_ids.insert_one({"_id": {"b": 2, "a": [True, 1]}})
    assert len(nested_ids.find()) == 2


def test_delete_one_and_many_report_deleted_counts() -> None:
    collection = Collection()
    collection.insert_many(
        [{"_id": 1, "kind": "x"}, {"_id": 2, "kind": "x"}, {"_id": 3, "kind": "y"}]
    )
    assert collection.delete_one({"kind": "x"}).deleted_count == 1
    assert collection.delete_many({"kind": "x"}).deleted_count == 1
    assert [doc["_id"] for doc in collection.find()] == [3]
