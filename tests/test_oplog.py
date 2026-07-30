"""Oplog entries are deterministic state assignments, not user commands."""

import pytest

from minimongodb import Collection
from minimongodb.oplog import Oplog, replay


def test_writes_emit_ordered_entries_per_affected_document() -> None:
    collection = Collection("items")
    collection.insert_many([{"_id": 1, "n": 1}, {"_id": 2, "n": 1}])
    collection.update_many({}, {"$inc": {"n": 1}})
    collection.delete_one({"_id": 1})

    assert [entry.sequence for entry in collection.oplog] == [1, 2, 3, 4, 5]
    assert [entry.operation for entry in collection.oplog] == [
        "insert",
        "insert",
        "update",
        "update",
        "delete",
    ]


def test_inc_is_rewritten_to_an_idempotent_set_result() -> None:
    collection = Collection("counters")
    collection.insert_one({"_id": "visits", "count": 2})
    collection.update_one({"_id": "visits"}, {"$inc": {"count": 3}})

    entry = list(collection.oplog)[-1]
    assert entry.operation == "update"
    assert entry.payload == {"$set": {"count": 5}}
    assert "$inc" not in entry.payload


def test_replaying_the_same_oplog_twice_has_the_same_result() -> None:
    source = Collection("people")
    source.insert_many([{"_id": 1, "n": 1}, {"_id": 2, "n": 10}])
    source.update_one({"_id": 1}, {"$inc": {"n": 2}})
    source.replace_one({"_id": 2}, {"n": 11})
    source.delete_one({"_id": 2})

    target = Collection("people", oplog=Oplog())
    replay(source.oplog, target)
    once = target.find()
    replay(source.oplog, target)

    assert target.find() == once == [{"_id": 1, "n": 3}]
    # Recovery actions must not recursively create a second oplog.
    assert list(target.oplog) == []


def test_post_image_keeps_only_the_final_state_for_a_repeated_path() -> None:
    source = Collection("items")
    source.insert_one({"_id": 1, "value": "old"})
    source.update_one(
        {"_id": 1},
        {"$unset": {"value": ""}, "$set": {"value": "final"}},
    )
    entry = list(source.oplog)[-1]
    assert entry.payload == {"$set": {"value": "final"}}

    target = Collection("items", oplog=Oplog())
    replay(source.oplog, target)
    replay(source.oplog, target)
    assert target.find_one({"_id": 1})["value"] == "final"


def test_batch_stops_at_first_durability_failure_and_keeps_committed_prefix() -> None:
    def durable_append(entry) -> None:
        if entry.sequence == 2:
            raise OSError("injected journal failure")

    oplog = Oplog(listener=durable_append)
    collection = Collection("items", oplog=oplog)

    with pytest.raises(OSError, match="injected journal failure"):
        collection.insert_many([{"_id": 1}, {"_id": 2}, {"_id": 3}])

    assert collection.find() == [{"_id": 1}]
    assert [entry.sequence for entry in oplog] == [1]
    assert oplog.last_sequence == 1


@pytest.mark.parametrize("operation", ["update", "delete"])
def test_multi_document_mutation_keeps_only_durable_prefix(operation: str) -> None:
    fail_at: int | None = None

    def durable_append(entry) -> None:
        if entry.sequence == fail_at:
            raise OSError("injected journal failure")

    oplog = Oplog(listener=durable_append)
    collection = Collection("items", oplog=oplog)
    collection.insert_many(
        [
            {"_id": 1, "state": "old"},
            {"_id": 2, "state": "old"},
            {"_id": 3, "state": "old"},
        ]
    )
    fail_at = 5

    with pytest.raises(OSError, match="injected journal failure"):
        if operation == "update":
            collection.update_many({}, {"$set": {"state": "new"}})
        else:
            collection.delete_many({})

    if operation == "update":
        assert collection.find() == [
            {"_id": 1, "state": "new"},
            {"_id": 2, "state": "old"},
            {"_id": 3, "state": "old"},
        ]
    else:
        assert collection.find() == [
            {"_id": 2, "state": "old"},
            {"_id": 3, "state": "old"},
        ]
    assert [entry.sequence for entry in oplog] == [1, 2, 3, 4]
    assert oplog.last_sequence == 4
