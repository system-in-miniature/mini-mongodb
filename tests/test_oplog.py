"""Oplog entries are deterministic state assignments, not user commands."""

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
