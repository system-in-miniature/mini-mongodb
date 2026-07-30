"""Executable contract for MiniMongoDB's deliberately small BSON model."""

import pytest

from minimongodb.bson import (
    MISSING,
    CounterObjectIdGenerator,
    ObjectId,
    bson_compare,
    clone_document,
    get_path,
    set_path,
    type_tag,
    unset_path,
)
from minimongodb.errors import PathError


def test_object_ids_come_only_from_the_injected_counter() -> None:
    generator = CounterObjectIdGenerator(start=40)
    assert generator() == ObjectId(40)
    assert generator() == ObjectId(41)
    assert str(ObjectId(41)) == "000000000000000000000029"


def test_type_tags_and_simplified_cross_type_order_are_explicit() -> None:
    values = [None, 1, "a", {"a": 1}, [1], False, ObjectId(1)]
    assert [type_tag(value) for value in values] == [
        "null",
        "number",
        "string",
        "document",
        "array",
        "bool",
        "objectId",
    ]
    assert all(bson_compare(left, right) < 0 for left, right in zip(values, values[1:]))


def test_clone_document_breaks_nested_aliases() -> None:
    original = {"nested": {"items": [1]}}
    copied = clone_document(original)
    copied["nested"]["items"].append(2)
    assert original == {"nested": {"items": [1]}}


def test_document_validation_rejects_unsupported_nested_values() -> None:
    with pytest.raises(TypeError, match="unsupported BSON value"):
        clone_document({"nested": {"not_bson": {1, 2}}})


def test_exact_document_equality_preserves_field_order() -> None:
    from minimongodb.bson import bson_equal

    assert not bson_equal({"a": 1, "b": 2}, {"b": 2, "a": 1})


def test_dotted_paths_read_write_and_unset_array_indexes() -> None:
    document = {"profile": {"names": [{"first": "Ada"}]}}
    assert get_path(document, "profile.names.0.first") == "Ada"
    assert get_path(document, "profile.missing") is MISSING

    set_path(document, "profile.names.0.first", "Grace")
    set_path(document, "profile.city", "London")
    assert document["profile"] == {
        "names": [{"first": "Grace"}],
        "city": "London",
    }
    assert unset_path(document, "profile.names.0.first") is True
    assert get_path(document, "profile.names.0.first") is MISSING


def test_path_writer_rejects_non_numeric_list_segments() -> None:
    with pytest.raises(PathError):
        set_path({"items": [1]}, "items.name", "bad")
