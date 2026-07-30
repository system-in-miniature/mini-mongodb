# Chapter 2: The Document Model

[中文版](../zh/tutorial/02-document-model.md)

Every higher-level operation depends on a precise answer to three questions:
which values are legal, when are two values equal, and how does a field path
select a nested value? MiniMongoDB keeps those answers in
`src/minimongodb/bson/`. This chapter develops the value model before queries
and updates begin using it in different ways.

## Learning objectives

By the end of this chapter, you will be able to:

- list MiniMongoDB's supported BSON-shaped type tags and comparison order;
- explain why `True`, `1`, documents, and arrays need typed equality;
- distinguish exact value equality from dotted-path selection;
- trace `get_path`, `set_path`, and query-specific `resolve_path`; and
- identify where MiniMongoDB intentionally differs from real BSON.

## Values have explicit tags

`src/minimongodb/bson/types.py::type_tag` accepts seven categories:
`null`, `number`, `string`, `document`, `array`, `bool`, and `objectId`.
Python values provide the representation—`dict` for documents and `list` for
arrays—but the database does not simply inherit all Python behavior. Sets,
tuples, bytes, datetimes, non-string document keys, and arbitrary objects are
rejected.

The order of checks in `type_tag` matters. Python makes `bool` a subclass of
`int`, so testing for numbers first would label `True` as a number. MiniMongoDB
tests `bool` first and gives it a separate tag. That distinction propagates to
equality, identity indexes, persistence, and sorting.

`src/minimongodb/bson/types.py::clone_document` calls the recursive
`_validate_tree` before `deepcopy`. Validation is therefore not limited to the
root. A set nested three arrays deep is still rejected before storage. The
supported object graph is value-like and acyclic under normal use, which makes
a deep copy a clear teaching representation of ownership transfer.

MiniMongoDB's `ObjectId` is a frozen value containing a non-negative integer
that fits in 96 bits. `ObjectId.__str__` renders 24 hexadecimal digits, so the
shape is familiar. `CounterObjectIdGenerator.__call__` supplies monotonically
increasing values and is injectable for deterministic tests. Shape is not
provenance: a real MongoDB ObjectId contains timestamp, random/process, and
counter material; this one deliberately does not.

## Exact equality is BSON-shaped

`src/minimongodb/bson/types.py::bson_equal` begins by comparing type tags.
Consequently `True` and `1` are different even though Python says
`True == 1`. Numeric int and float values share the `number` tag and compare by
numeric value, subject to explicit NaN handling.

Documents are compared in insertion order. The function checks the ordered key
lists and then recursively compares corresponding values:

```python
if isinstance(left, dict):
    return list(left.keys()) == list(right.keys()) and all(
        bson_equal(left[key], right[key]) for key in left
    )
```

Thus `{"a": 1, "b": 2}` is not exactly equal to
`{"b": 2, "a": 1}`. Arrays compare element by element and remain
order-sensitive. This exact equality becomes important when a query operand is
itself a document or array. A literal document means “equal to this whole
embedded value,” not “contains these fields.”

Hash tables need hashable keys, but BSON-shaped values can contain dictionaries
and lists. `src/minimongodb/bson/types.py::canonical_key` recursively converts
a value into a tuple beginning with its type tag. Numbers receive special
normalization so ordinary equal int/float values share identity, NaNs converge,
and large integers do not accidentally collapse through an imprecise float.
Documents preserve field order in their canonical form; arrays preserve
element order.

`src/minimongodb/index/id_index.py::IdIndex` uses this key for uniqueness and
lookup. The typed prefix is why `_id=True` and `_id=1` can coexist, while
`_id=1` and `_id=1.0` usually conflict. Canonicalization is an indexing
representation of `bson_equal`, not a new public equality rule.

## A deliberately small comparison order

Range predicates and aggregation sorting need ordering, not only equality.
`src/minimongodb/bson/types.py::bson_compare` first compares positions in
`_TYPE_ORDER`:

```text
null < number < string < document < array < bool < objectId
```

Values with the same tag are compared recursively. Documents compare their
key/value sequence, arrays compare elements lexicographically, and numeric
comparison treats NaN explicitly to remain deterministic.

This global order is a teaching choice, not MongoDB parity. Real BSON supports
many more types and has a documented BSON comparison order. More importantly,
MongoDB comparison query predicates usually apply type bracketing: a numeric
range normally compares numeric fields rather than walking a global order
across strings and documents. MiniMongoDB exposes its global order directly.
Code that relies on cross-type range matches here is not portable MQL.

## Dotted paths: one notation, two read semantics

CRUD updates and aggregation expressions use
`src/minimongodb/bson/path.py::get_path`. It splits a non-empty dotted string,
walks dictionary keys, and accepts a numeric segment when the current container
is a list. Missing keys or indexes return the sentinel `MISSING`, which is
different from a stored `None`.

That distinction lets an update tell “field absent” from “field explicitly
null.” It also lets aggregation omit a missing projected field while retaining
a null field. A private sentinel is safer than choosing an ordinary user value
as “not found.”

`set_path` traverses existing containers and can create missing dictionary
parents. It will not guess how to create or extend arrays. If the current
container is a list, the segment must be numeric and the position must already
exist. `unset_path` deletes a dictionary key, but when it targets an array
position it writes `None` so later positions do not shift.

Query matching needs a different read operation:
`src/minimongodb/query/matcher.py::resolve_path`. When a nonnumeric field is
applied to an array, it recursively applies the same remaining path to every
element. For:

```python
{"items": [{"sku": "A"}, {"sku": "B"}]}
```

`resolve_path(document, "items.sku")` yields both `"A"` and `"B"`. By contrast,
the general-purpose `get_path` returns one value or `MISSING`; it does not
perform query fan-out. Keeping these functions separate prevents aggregation
and update code from accidentally inheriting matcher-only array semantics.

This is a recurring architectural lesson: shared syntax does not imply shared
cardinality. Both functions understand dots and numeric array indexes, but
only the matcher path can return several candidates.

## Compared with real MongoDB

Real MongoDB stores binary BSON with types absent here, including date, binary,
decimal, regex, timestamp, MinKey, and MaxKey. MiniMongoDB's tagged JSON
persistence is inspectable but neither BSON binary nor wire-compatible.
MongoDB's ObjectId generation is nondeterministic and time-bearing; the local
counter is semantically opposite in provenance.

The useful correspondences are narrower. Documents and arrays remain distinct
typed values. Embedded-document equality is whole-value and field-order
sensitive. Dot notation selects nested fields, and numeric segments can address
array positions. Those are real concepts represented by smaller code.

Read the exact boundary in
[BSON and identity differences](../DIFFERENCES.md#bson-and-identity-differences)
and [query differences](../DIFFERENCES.md#query-differences). The
`bson.types`, `ObjectId`, and `bson.path` rows in the
[mapping table](../mapping.md#minimongodb--mongodb-mapping) classify the
relationships.

One particularly important mismatch is null versus missing. In real MongoDB,
`{field: null}` also matches documents where the field is missing.
MiniMongoDB's literal-null equality requires a present `None`; missing is
queried with `$exists: false`.

## Hands-on experiment: inspect tags, order, and paths

Run:

```bash
UV_CACHE_DIR=/tmp/minimongodb-uv-cache uv run python - <<'PY'
from minimongodb import ObjectId
from minimongodb.bson import MISSING, bson_compare, bson_equal, get_path, type_tag

values = [None, 1, "a", {"a": 1}, [1], False, ObjectId(1)]
print("tags:", [type_tag(value) for value in values])
print("ascending:", all(bson_compare(a, b) < 0 for a, b in zip(values, values[1:])))
print("True equals 1:", bson_equal(True, 1))
document = {"profile": {"names": [{"first": "Ada"}]}, "nullish": None}
print("nested:", get_path(document, "profile.names.0.first"))
print("missing sentinel:", get_path(document, "profile.city") is MISSING)
print("null is missing:", get_path(document, "nullish") is MISSING)
PY
```

Measured output:

```text
tags: ['null', 'number', 'string', 'document', 'array', 'bool', 'objectId']
ascending: True
True equals 1: False
nested: Ada
missing sentinel: True
null is missing: False
```

The output proves the project-specific tag order and the null/missing
distinction. It does not prove real BSON comparison parity.

## Exercises

### 1. Understanding: equality versus selection

Why can an exact comparison of `{"city": "London"}` fail against
`{"city": "London", "role": "engineer"}` while a dotted query on
`profile.city` succeeds?

??? note "Reference answer"

    Exact document equality compares the complete ordered field/value
    sequence. A dotted path first selects the nested `city` scalar, so the
    unrelated `role` field is outside the value being compared.

### 2. Understanding: typed identity

Predict whether `_id=True` conflicts with `_id=1`, and whether `_id=1`
conflicts with `_id=1.0`. Verify with `Collection.insert_one`.

??? note "Reference answer"

    `True` and `1` have different tags and may coexist. Ordinary `1` and `1.0`
    share numeric BSON equality and therefore conflict in the `_id` index.
    Acceptance is two successful inserts for the first pair and a
    `DuplicateKeyError` for the second pair.

### 3. Hands-on: add a teaching value type on paper

Draft, but do not apply, a diff that adds a `date` tag. Identify changes needed
in `type_tag`, `_TYPE_ORDER`, equality/comparison, `canonical_key`, and the
storage codec. Acceptance: the proposed diff names every layer and includes at
least one round-trip and one ordering test.

??? note "Reference answer"

    A complete proposal adds a `datetime` check before unsupported-value
    rejection, assigns an explicit order position, defines deterministic
    same-tag comparison and canonical encoding, adds `date` branches to
    `_to_node/_from_node`, and tests clone validation, equality, comparison,
    canonical `_id` behavior, and checkpoint/journal round trips. Merely
    changing `type_tag` is incomplete because persistence would reject the
    new node.

### 4. Hands-on: path mutation without source edits

Use `get_path`, `set_path`, and `unset_path` on a local dictionary. Acceptance:
create `profile.city`, change `names.0.first`, unset the array element at
`values.1`, and print a `None` placeholder rather than a shortened array.

??? note "Reference answer"

    Start with
    `{"profile": {"names": [{"first": "Ada"}]}, "values": [1, 2, 3]}`.
    After the operations the relevant shape is
    `{"profile": {"names": [{"first": "Grace"}], "city": "London"},
    "values": [1, None, 3]}`.

## Summary

MiniMongoDB overlays explicit database semantics on Python containers.
`type_tag`, `bson_equal`, `bson_compare`, and `canonical_key` keep type,
equality, ordering, and hash identity aligned. `get_path` performs singular
document traversal, while matcher `resolve_path` may fan out through arrays.
The next chapter uses those primitives to explain the book's central query
lesson: why arrays sometimes expand into candidate elements and sometimes
remain exact whole values.
