"""The project's central lesson: arrays fan out, literal documents do not."""

from minimongodb.query import matches


def test_scalar_equality_automatically_matches_an_array_element() -> None:
    assert matches({"tags": ["database", "python"]}, {"tags": "python"})
    assert not matches({"tags": ["database", "python"]}, {"tags": "rust"})


def test_scalar_comparison_automatically_matches_an_array_element() -> None:
    assert matches({"scores": [2, 8]}, {"scores": {"$gt": 7}})


def test_literal_array_still_requires_whole_array_equality() -> None:
    document = {"tags": ["database", "python"]}
    assert matches(document, {"tags": ["database", "python"]})
    assert not matches(document, {"tags": ["python", "database"]})


def test_nested_document_literal_is_an_exact_whole_value_match() -> None:
    document = {"profile": {"name": "Ada", "city": "London"}}
    assert not matches(document, {"profile": {"name": "Ada"}})
    assert matches(document, {"profile": {"name": "Ada", "city": "London"}})


def test_dotted_path_selects_inside_nested_document_instead() -> None:
    document = {"profile": {"name": "Ada", "city": "London"}}
    assert matches(document, {"profile.name": "Ada"})


def test_dotted_path_fans_out_through_arrays_of_documents() -> None:
    document = {"items": [{"sku": "A"}, {"sku": "B"}]}
    assert matches(document, {"items.sku": "B"})
