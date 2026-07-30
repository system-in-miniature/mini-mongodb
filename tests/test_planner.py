"""Planner selection is deterministic and explain uses MongoDB terminology."""

from minimongodb import Collection


def _collection() -> Collection:
    collection = Collection("events")
    collection.insert_many(
        [
            {"_id": 1, "tenant": "a", "kind": "rare"},
            {"_id": 2, "tenant": "a", "kind": "common"},
            {"_id": 3, "tenant": "b", "kind": "common"},
            {"_id": 4, "tenant": "b", "kind": "common"},
        ]
    )
    return collection


def test_explain_changes_from_collscan_to_selective_ixscan() -> None:
    collection = _collection()

    before = collection.explain({"kind": "rare"})
    assert before["queryPlanner"]["winningPlan"] == {"stage": "COLLSCAN"}
    assert before["executionStats"] == {
        "nReturned": 1,
        "keysExamined": 0,
        "docsExamined": 4,
    }

    collection.create_index("kind")
    after = collection.explain({"kind": "rare"})
    assert after["queryPlanner"]["winningPlan"] == {
        "stage": "IXSCAN",
        "indexName": "kind_1",
        "keyPattern": {"kind": 1},
        "indexBounds": {"kind": "rare"},
    }
    assert after["executionStats"] == {
        "nReturned": 1,
        "keysExamined": 1,
        "docsExamined": 1,
    }


def test_compound_index_requires_a_leftmost_prefix() -> None:
    collection = _collection()
    collection.create_index([("tenant", 1), ("kind", 1)])

    prefix = collection.explain({"tenant": "a", "kind": "rare"})
    assert prefix["queryPlanner"]["winningPlan"]["stage"] == "IXSCAN"
    assert prefix["queryPlanner"]["winningPlan"]["indexName"] == "tenant_1_kind_1"

    no_prefix = collection.explain({"kind": "rare"})
    assert no_prefix["queryPlanner"]["winningPlan"] == {"stage": "COLLSCAN"}


def test_unselective_index_loses_to_collection_scan() -> None:
    collection = _collection()
    collection.create_index("kind")
    explanation = collection.explain({"kind": {"$in": ["rare", "common"]}})
    assert explanation["queryPlanner"]["winningPlan"] == {"stage": "COLLSCAN"}


def test_automatic_id_index_serves_identity_equality() -> None:
    collection = _collection()
    explanation = collection.explain({"_id": 3})
    assert explanation["queryPlanner"]["winningPlan"] == {
        "stage": "IXSCAN",
        "indexName": "_id_",
        "keyPattern": {"_id": 1},
        "indexBounds": {"_id": 3},
    }
    assert explanation["executionStats"] == {
        "nReturned": 1,
        "keysExamined": 1,
        "docsExamined": 1,
    }


def test_id_index_falls_back_for_scalar_matching_inside_array_ids() -> None:
    collection = Collection("array_ids")
    collection.insert_many([{"_id": [1, 2], "value": "array"}, {"_id": 3}])

    assert collection.find({"_id": 1}) == [
        {"_id": [1, 2], "value": "array"}
    ]
    assert collection.find({"_id": {"$eq": 2}}) == [
        {"_id": [1, 2], "value": "array"}
    ]
    assert collection.find({"_id": {"$in": [1]}}) == [
        {"_id": [1, 2], "value": "array"}
    ]
    assert collection.explain({"_id": 1})["queryPlanner"]["winningPlan"] == {
        "stage": "COLLSCAN"
    }
    assert collection.explain({"_id": [1, 2]})["queryPlanner"]["winningPlan"][
        "indexName"
    ] == "_id_"


def test_multikey_planner_falls_back_when_leaf_bounds_cannot_preserve_matching() -> None:
    collection = Collection("arrays")
    collection.insert_many(
        [{"_id": 1, "values": [1, 20]}, {"_id": 2, "values": [3, 4]}]
    )
    literal_query = {"values": [1, 20]}
    cross_element_query = {"values": {"$gt": 10, "$lt": 5}}
    expected_literal = collection.find(literal_query)
    expected_cross_element = collection.find(cross_element_query)

    collection.create_index("values")

    assert collection.find(literal_query) == expected_literal
    assert collection.find(cross_element_query) == expected_cross_element
    assert collection.explain(literal_query)["queryPlanner"]["winningPlan"] == {
        "stage": "COLLSCAN"
    }
    assert collection.explain(cross_element_query)["queryPlanner"][
        "winningPlan"
    ] == {"stage": "COLLSCAN"}
