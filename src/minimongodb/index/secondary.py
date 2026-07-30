"""Canonical ordered secondary indexes with explicit multikey expansion.

One document can own several index entries when a selected value is an array.
Entries retain their BSON-shaped values for ordered scans, while ownership and
uniqueness use the same type-tagged ``canonical_key`` representation as
``_id``.  This separation keeps comparison order and equality identity honest.
"""

from __future__ import annotations

from itertools import product
from typing import Any, Iterable

from minimongodb.bson import bson_compare, bson_equal, canonical_key
from minimongodb.errors import DuplicateKeyError
CompoundKey = tuple[tuple[Any, ...], ...]
DocumentKey = tuple[Any, ...]


def normalize_index_spec(
    keys: str | dict[str, int] | Iterable[tuple[str, int]],
) -> tuple[tuple[str, int], ...]:
    """Normalize the public shorthand to an ordered ascending key pattern."""

    if isinstance(keys, str):
        items = [(keys, 1)]
    elif isinstance(keys, dict):
        items = list(keys.items())
    else:
        try:
            items = list(keys)
        except TypeError as error:
            raise TypeError("index keys must be a field or ordered key pairs") from error
    if not items:
        raise ValueError("an index needs at least one field")
    if any(
        not isinstance(item, tuple)
        or len(item) != 2
        or not isinstance(item[0], str)
        or not item[0]
        or item[1] != 1
        for item in items
    ):
        raise ValueError("only non-empty ascending field paths are supported")
    fields = [field for field, _direction in items]
    if len(set(fields)) != len(fields):
        raise ValueError("an index cannot repeat a field path")
    return tuple(items)


def default_index_name(spec: tuple[tuple[str, int], ...]) -> str:
    return "_".join(f"{field}_{direction}" for field, direction in spec)


def _leaves(value: Any) -> list[Any]:
    if isinstance(value, list):
        return [leaf for child in value for leaf in _leaves(child)]
    return [value]


def _field_values(document: dict[str, Any], path: str) -> tuple[list[Any], bool]:
    selected, traversed_array = _resolve_index_path(document, path.split("."))
    if not selected:
        # Like a non-sparse MongoDB index, missing fields occupy a null-like key.
        return [None], traversed_array
    values = [leaf for value in selected for leaf in _leaves(value)]
    expanded_value = any(isinstance(value, list) for value in selected)
    return values or [None], traversed_array or expanded_value


def _resolve_index_path(
    current: Any, parts: list[str]
) -> tuple[list[Any], bool]:
    if not parts:
        return [current], isinstance(current, list)
    part, rest = parts[0], parts[1:]
    if isinstance(current, dict):
        if part not in current:
            return [], False
        return _resolve_index_path(current[part], rest)
    if isinstance(current, list):
        if part.isdigit():
            position = int(part)
            if position >= len(current):
                return [], True
            values, _child_array = _resolve_index_path(current[position], rest)
            return values, True
        values: list[Any] = []
        for element in current:
            selected, _child_array = _resolve_index_path(element, parts)
            values.extend(selected)
        return values, True
    return [], False


class SecondaryIndex:
    """An ordered key pattern backed by canonical buckets of document ids."""

    def __init__(
        self,
        spec: tuple[tuple[str, int], ...],
        *,
        name: str,
        unique: bool = False,
    ) -> None:
        self.spec = spec
        self.name = name
        self.unique = unique
        self.is_multikey = False
        self._values: dict[CompoundKey, tuple[Any, ...]] = {}
        self._owners: dict[CompoundKey, set[DocumentKey]] = {}

    @property
    def key_pattern(self) -> dict[str, int]:
        return dict(self.spec)

    @property
    def entry_count(self) -> int:
        return len(self._owners)

    def document_keys(
        self, document: dict[str, Any]
    ) -> list[tuple[CompoundKey, tuple[Any, ...]]]:
        entries, _multikey = self._document_entries(document)
        return entries

    def _document_entries(
        self, document: dict[str, Any]
    ) -> tuple[list[tuple[CompoundKey, tuple[Any, ...]]], bool]:
        selected = [
            _field_values(document, field) for field, _direction in self.spec
        ]
        combinations = product(*(values for values, _expanded in selected))
        deduplicated: dict[CompoundKey, tuple[Any, ...]] = {}
        for values in combinations:
            compound = tuple(canonical_key(value) for value in values)
            deduplicated.setdefault(compound, values)
        return list(deduplicated.items()), any(
            expanded for _values, expanded in selected
        )

    def validate_documents(self, documents: Iterable[dict[str, Any]]) -> None:
        """Check a prospective batch without making any entry visible."""

        if not self.unique:
            return
        owners = {key: set(value) for key, value in self._owners.items()}
        for document in documents:
            document_id = canonical_key(document["_id"])
            for compound, values in self.document_keys(document):
                conflicting = owners.get(compound, set()) - {document_id}
                if conflicting:
                    raise DuplicateKeyError(
                        f"duplicate key for index {self.name}: {values!r}"
                    )
                owners.setdefault(compound, set()).add(document_id)

    def validate_replace(
        self, original: dict[str, Any], replacement: dict[str, Any]
    ) -> None:
        if not self.unique:
            return
        original_id = canonical_key(original["_id"])
        for compound, values in self.document_keys(replacement):
            conflicting = self._owners.get(compound, set()) - {original_id}
            if conflicting:
                raise DuplicateKeyError(
                    f"duplicate key for index {self.name}: {values!r}"
                )

    def add(self, document: dict[str, Any]) -> None:
        entries, expanded_array = self._document_entries(document)
        if expanded_array:
            self.is_multikey = True
        document_id = canonical_key(document["_id"])
        for compound, values in entries:
            self._values.setdefault(compound, values)
            self._owners.setdefault(compound, set()).add(document_id)

    def remove(self, document: dict[str, Any]) -> None:
        document_id = canonical_key(document["_id"])
        for compound, _values in self.document_keys(document):
            owners = self._owners.get(compound)
            if owners is None:
                continue
            owners.discard(document_id)
            if not owners:
                self._owners.pop(compound)
                self._values.pop(compound)

    def replace(
        self, original: dict[str, Any], replacement: dict[str, Any]
    ) -> None:
        self.remove(original)
        self.add(replacement)

    def prefix_length(self, query: dict[str, Any]) -> int:
        """Return the usable leftmost prefix, stopping after a range predicate."""

        length = 0
        for field, _direction in self.spec:
            if field not in query or field.startswith("$"):
                break
            condition = query[field]
            if self.is_multikey and isinstance(condition, list):
                break
            if isinstance(condition, dict):
                operators = set(condition)
                if not operators or any(not key.startswith("$") for key in operators):
                    length += 1
                    continue
                if not operators <= {"$eq", "$in", "$gt", "$gte", "$lt", "$lte"}:
                    break
                if self.is_multikey and (
                    len(operators) > 1
                    or any(
                        (
                            operator == "$in"
                            and isinstance(operand, list)
                            and any(isinstance(option, list) for option in operand)
                        )
                        or (operator != "$in" and isinstance(operand, list))
                        for operator, operand in condition.items()
                    )
                ):
                    # Without $elemMatch, different array elements may satisfy
                    # different predicates. Leaf-key intersection would drop
                    # valid documents, so correctness requires a collection scan.
                    break
                length += 1
                if operators - {"$eq", "$in"}:
                    break
            else:
                length += 1
        return length

    def scan(
        self, query: dict[str, Any], prefix_length: int
    ) -> tuple[set[DocumentKey], int]:
        """Scan matching ordered keys and return candidate owners plus key count."""

        candidates: set[DocumentKey] = set()
        keys_examined = 0
        for compound in sorted(self._owners, key=self._sort_token):
            values = self._values[compound]
            if all(
                _condition_matches(values[position], query[field])
                for position, (field, _direction) in enumerate(
                    self.spec[:prefix_length]
                )
            ):
                keys_examined += 1
                candidates.update(self._owners[compound])
        return candidates, keys_examined

    def _sort_token(self, compound: CompoundKey) -> "_CompoundSort":
        return _CompoundSort(self._values[compound])


class _CompoundSort:
    """Small comparison wrapper so ordered scans use BSON comparison."""

    def __init__(self, values: tuple[Any, ...]) -> None:
        self.values = values

    def __lt__(self, other: "_CompoundSort") -> bool:
        for left, right in zip(self.values, other.values):
            compared = bson_compare(left, right)
            if compared:
                return compared < 0
        return len(self.values) < len(other.values)


def _condition_matches(value: Any, condition: Any) -> bool:
    if not isinstance(condition, dict) or not any(
        isinstance(key, str) and key.startswith("$") for key in condition
    ):
        return bson_equal(value, condition)
    for operator, operand in condition.items():
        if operator == "$eq" and not bson_equal(value, operand):
            return False
        if operator == "$in":
            if not isinstance(operand, list) or not any(
                bson_equal(value, option) for option in operand
            ):
                return False
        if operator in {"$gt", "$gte", "$lt", "$lte"}:
            compared = bson_compare(value, operand)
            accepted = {
                "$gt": compared > 0,
                "$gte": compared >= 0,
                "$lt": compared < 0,
                "$lte": compared <= 0,
            }[operator]
            if not accepted:
                return False
    return True
