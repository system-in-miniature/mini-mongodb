"""Secondary indexes preserve BSON identity and expand multikey documents."""

from pathlib import Path

import pytest

from minimongodb import Collection, Database
from minimongodb.errors import DuplicateKeyError
from minimongodb.oplog import Oplog


def test_single_and_compound_indexes_accept_dotted_paths() -> None:
    collection = Collection("people")
    collection.insert_many(
        [
            {"_id": 1, "team": "db", "profile": {"city": "Paris"}},
            {"_id": 2, "team": "db", "profile": {"city": "Oslo"}},
            {"_id": 3, "team": "web", "profile": {"city": "Paris"}},
        ]
    )

    assert collection.create_index("profile.city") == "profile.city_1"
    assert (
        collection.create_index([("team", 1), ("profile.city", 1)])
        == "team_1_profile.city_1"
    )
    assert collection.find({"team": "db", "profile.city": "Oslo"}) == [
        {"_id": 2, "team": "db", "profile": {"city": "Oslo"}}
    ]


def test_multikey_index_emits_multiple_deduplicated_keys_per_document() -> None:
    collection = Collection("articles")
    collection.insert_many(
        [
            {"_id": 1, "tags": ["database", "python", "database"]},
            {"_id": 2, "tags": ["storage"]},
            {"_id": 3, "tags": ["database"]},
        ]
    )
    collection.create_index("tags")

    explanation = collection.explain({"tags": "database"})
    assert explanation["queryPlanner"]["winningPlan"]["stage"] == "IXSCAN"
    assert explanation["executionStats"] == {
        "nReturned": 2,
        "keysExamined": 1,
        "docsExamined": 2,
    }
    assert [document["_id"] for document in collection.find({"tags": "database"})] == [
        1,
        3,
    ]


def test_multikey_metadata_tracks_array_expansion_not_distinct_key_count() -> None:
    collection = Collection("articles")
    collection.insert_one({"_id": 1, "tags": ["same", "same"]})
    collection.create_index("tags")
    assert collection.index_information()["tags_1"]["multikey"] is True
    assert collection.index_information()["tags_1"]["entries"] == 1


def test_unique_index_uses_canonical_bson_keys_and_multikey_ownership() -> None:
    collection = Collection("users")
    collection.create_index("handle", unique=True)
    collection.insert_many([{"_id": 1, "handle": True}, {"_id": 2, "handle": 1}])
    with pytest.raises(
        DuplicateKeyError, match=r"duplicate key for index handle_1"
    ):
        collection.insert_one({"_id": 3, "handle": 1.0})

    tags = Collection("tags")
    tags.create_index("values", unique=True)
    tags.insert_one({"_id": 1, "values": ["same", "same"]})
    with pytest.raises(
        DuplicateKeyError, match=r"duplicate key for index values_1"
    ):
        tags.insert_one({"_id": 2, "values": ["same"]})


def test_unique_index_validates_existing_documents_and_whole_insert_batch() -> None:
    collection = Collection("users")
    collection.insert_many(
        [{"_id": 1, "email": "same"}, {"_id": 2, "email": "same"}]
    )
    with pytest.raises(DuplicateKeyError):
        collection.create_index("email", unique=True)

    clean = Collection("users")
    clean.create_index("email", unique=True)
    with pytest.raises(DuplicateKeyError):
        clean.insert_many(
            [{"_id": 1, "email": "same"}, {"_id": 2, "email": "same"}]
        )
    assert clean.find() == []


def test_updates_and_deletes_maintain_unique_secondary_indexes() -> None:
    collection = Collection("users")
    collection.create_index("email", unique=True)
    collection.insert_many(
        [{"_id": 1, "email": "one"}, {"_id": 2, "email": "two"}]
    )

    with pytest.raises(DuplicateKeyError):
        collection.update_one({"_id": 1}, {"$set": {"email": "two"}})
    assert collection.find_one({"_id": 1})["email"] == "one"

    collection.delete_one({"_id": 2})
    collection.update_one({"_id": 1}, {"$set": {"email": "two"}})
    assert collection.find({"email": "two"}) == [{"_id": 1, "email": "two"}]


def test_secondary_index_is_not_published_when_journal_append_fails() -> None:
    state = {"fail": False}

    def listener(entry) -> None:
        if state["fail"]:
            raise OSError("injected journal failure")

    collection = Collection("items", oplog=Oplog(listener=listener))
    collection.create_index("kind")
    collection.insert_one({"_id": 1, "kind": "visible"})
    state["fail"] = True

    with pytest.raises(OSError, match="injected journal failure"):
        collection.insert_one({"_id": 2, "kind": "hidden"})

    assert collection.find({"kind": "hidden"}) == []
    assert collection.explain({"kind": "hidden"})["executionStats"]["nReturned"] == 0


@pytest.mark.parametrize("checkpointed", [False, True])
def test_index_definition_survives_journal_and_checkpoint_recovery(
    tmp_path: Path, checkpointed: bool
) -> None:
    database = Database(tmp_path)
    articles = database["articles"]
    articles.create_index("tags", unique=True)
    articles.insert_many(
        [
            {"_id": 1, "tags": ["database", "storage"]},
            {"_id": 2, "tags": ["python"]},
        ]
    )
    if checkpointed:
        database.checkpoint()

    recovered = Database(tmp_path)["articles"]
    assert recovered.index_information()["tags_1"] == {
        "key": {"tags": 1},
        "unique": True,
        "multikey": True,
        "entries": 3,
    }
    assert recovered.explain({"tags": "database"})["queryPlanner"]["winningPlan"][
        "stage"
    ] == "IXSCAN"
    with pytest.raises(DuplicateKeyError):
        recovered.insert_one({"_id": 3, "tags": ["database"]})
