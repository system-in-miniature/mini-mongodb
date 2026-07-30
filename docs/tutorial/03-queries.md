# Chapter 3: Query Semantics

[中文版](../zh/tutorial/03-queries.md)

Document queries become subtle when one path can denote a scalar, an array, an
embedded document, or several values reached through an array of documents.
MiniMongoDB concentrates those rules in one small matcher. The planner may
choose candidates, but `src/minimongodb/query/matcher.py::matches` remains the
semantic authority.

## Learning objectives

By the end of this chapter, you will be able to:

- trace a query from `Collection.find` through planning to `matches`;
- distinguish scalar array matching, whole-array equality, whole-document
  equality, and dotted-path fan-out;
- explain the behavior of the supported field and logical operators;
- reason about missing fields, `$ne`, `$exists`, and `$not`; and
- identify query behavior that is intentionally nonportable to MongoDB.

## Planning does not define truth

`src/minimongodb/collection.py::Collection._run_query` normalizes `None` to an
empty query, validates syntax, and calls
`src/minimongodb/plan/__init__.py::choose_plan`. A plan either supplies no
candidate identifiers, meaning scan `_documents`, or supplies an identifier
set produced by an index. In both cases the final line filters candidates with
the same `matches(document, normalized)` call.

This division is essential. An index stores a projection of documents and can
produce false positives for richer query semantics. It may safely narrow the
work only when it cannot omit a true match. The matcher is the residual
predicate and final judge. Chapter 8 examines the planner; for now, treat it as
an optimization around a stable semantic core.

`Collection._run_query` walks stored documents in insertion order even after
an index supplies an unordered ownership set. As a result, adding an index can
change `docsExamined` but not matching semantics or public result order.

## From a dotted path to candidate values

For every ordinary field in a query,
`src/minimongodb/query/matcher.py::matches` calls `resolve_path`. A dictionary
consumes one field segment. A numeric segment selects one list position. A
nonnumeric segment applied to a list fans out: it applies the same remaining
path to every array element and concatenates their selected values.

Given:

```python
{"items": [{"sku": "A", "qty": 1}, {"sku": "B", "qty": 4}]}
```

the path `items.sku` resolves to candidate values `"A"` and `"B"`. A missing
path resolves to an empty list, not `[None]`. Presence is therefore
`bool(values)`, which powers `$exists`.

After resolution, `_field_matches` decides whether a condition is an operator
document or a literal value. A dictionary containing dollar-prefixed keys is
an operator document; mixing operator and literal keys is rejected. A plain
dictionary is a literal embedded-document value and uses exact BSON-shaped
equality.

## The array rule: expand only for scalar-like operands

`src/minimongodb/query/matcher.py::_array_candidates` contains the central
rule. If the stored selected value is a list and the expected query operand is
neither a list nor a dictionary, it recursively yields scalar leaves.
Otherwise it yields the stored value whole.

This produces four behaviors worth memorizing:

1. Stored `["database", "python"]` queried with scalar `"python"` matches an
   element automatically.
2. The same array queried with literal `["database", "python"]` compares the
   whole array, including order.
3. Stored `{"city": "London", "role": "engineer"}` queried with literal
   `{"city": "London"}` fails because documents compare as whole values.
4. Querying `profile.city` first selects `"London"`, so the unrelated `role`
   field no longer participates.

Nested arrays recursively expose scalar leaves for scalar operands in this
teaching subset. This compact rule is more permissive and less complete than
the full MongoDB matcher, but it demonstrates why “array equality” is not a
single operation. The operand's shape changes whether the stored array is a
container to traverse or a value to compare.

Range comparisons reuse this expansion.
`src/minimongodb/query/matcher.py::_compare` applies `bson_compare` to each
candidate and accepts if any candidate satisfies `$gt`, `$gte`, `$lt`, or
`$lte`. A type error becomes a nonmatch rather than a Python exception.

## Field operators

`_operator_matches` implements the supported set:

- `$eq` uses the equality behavior just described;
- `$gt`, `$gte`, `$lt`, and `$lte` use the project comparison order;
- `$in` accepts when any resolved value equals any option;
- `$ne` succeeds when no resolved value equals the operand;
- `$exists` compares requested boolean presence with `bool(values)`;
- field-level `$not` negates an operator document.

The placement of the presence check matters. `$ne` is evaluated before the
general “not present means false” branch, so a missing field matches
`{"field": {"$ne": value}}`. `$exists: false` also matches missing. Ordinary
equality, ranges, and `$in` require a present value.

An operator document combines its entries with `all`. For a scalar field,
`{"age": {"$gte": 18, "$lt": 65}}` is a familiar interval. For an array path,
however, separate operators can be satisfied by different elements because
MiniMongoDB has no `$elemMatch`. The document `{"scores": [2, 20]}` can satisfy
both `$gt: 10` and `$lt: 5`. This behavior has a MongoDB analogue outside
`$elemMatch`, but the miniature's recursive expansion and planner safeguards
are its own subset.

## Logical operators

At the top level, `matches` handles `$and` and `$or` arrays recursively.
Ordinary field conditions are already implicitly ANDed by the surrounding
loop. `$and` is useful when the same field must appear in separate expression
objects or when queries are assembled programmatically.

MiniMongoDB also accepts a project-specific top-level `$not` containing a query
document. It recursively matches the child and negates the result. Real
MongoDB does not support top-level `$not`; it supports `$nor` and field-level
`$not`. Any query using this local extension is intentionally nonportable.

Unsupported dollar-prefixed keys raise `InvalidQueryError`. At the start of
`matches`, the independent `validate_query` pass recursively validates every
logical branch and field-operator operand, including requirements such as
“`$in` must receive an array.” `_run_query` invokes `matches({}, query)` before
planning, so this complete validation also runs for an empty collection or a
zero-candidate index scan. A bad query must not become silently valid merely
because no data happened to be stored.

## Compared with real MongoDB

The scalar-versus-stored-array match and exact embedded-document equality are
useful MongoDB-shaped lessons. Dotted paths also fan out through arrays of
documents. However, MiniMongoDB implements only
`$eq/$gt/$gte/$lt/$lte/$ne/$in/$exists/$and/$or/$not`. It has no regex,
collation, `$elemMatch`, `$all`, `$size`, geospatial predicates, expression
queries, or full MQL grammar.

Real range predicates normally apply type bracketing; MiniMongoDB exposes its
small global cross-type order. Real `{field: null}` also matches missing
fields; here it matches only an explicit `None`. The top-level `$not` extension
is opposite to MongoDB syntax. `find` returns an eager list and has no cursor,
projection, sort, skip, limit, hint, or read concern.

The detailed contract is in
[query differences](../DIFFERENCES.md#query-differences). The matcher rows in
the [mapping](../mapping.md#minimongodb--mongodb-mapping) separately classify
scalar-array equality, embedded-document equality, range comparison, and
top-level `$not`; do not flatten those different parity levels into “queries
are MongoDB-compatible.”

## Hands-on experiment: three meanings of shape

Run the repository lab:

```bash
UV_CACHE_DIR=/tmp/minimongodb-uv-cache uv run python labs/lab_array_matching.py
```

Measured output:

```text
scalar array match: ['Ada']
  A scalar query inspects each stored array element automatically.
literal nested document: []
  A document literal means exact whole-document equality; extra keys matter.
dotted path match: ['Ada']
  A dotted path selects one nested field, so unrelated keys do not matter.
```

The first result comes from `_array_candidates`; the second from exact
`bson_equal` on the complete embedded document; the third from `resolve_path`
selecting a scalar before equality. The command uses only the in-process API.
It is not a socket or official-driver compatibility test.

## Exercises

### 1. Understanding: whole array or element?

For `{"tags": ["database", "python"]}`, predict results for queries
`{"tags": "python"}`, `{"tags": ["database", "python"]}`, and
`{"tags": ["python", "database"]}`. Explain which source function controls the
difference.

??? note "Reference answer"

    The first two match; the reversed literal array does not. Scalar
    `"python"` causes `_array_candidates` to expose elements. A list operand
    keeps the stored list whole, and `bson_equal` preserves array order.

### 2. Understanding: missing, null, and negative predicates

Evaluate an empty document against `{"x": None}`, `{"x": {"$exists": False}}`,
and `{"x": {"$ne": 3}}`.

??? note "Reference answer"

    Literal null is false because no value was resolved. `$exists: false` is
    true because presence is false. `$ne: 3` is true because no resolved value
    equals `3`. This differs from real MongoDB's null-or-missing behavior.

### 3. Hands-on: add `$nor` as a patch proposal

Draft a source-and-test diff, but do not modify `src/`, for top-level `$nor`.
Acceptance: it rejects a non-list operand, returns true only when none of its
child queries match, and includes positive, negative, and malformed tests.

??? note "Reference answer"

    In `matches`, add a branch adjacent to `$and/$or`:

    ```diff
    + elif key == "$nor":
    +     if not isinstance(condition, list):
    +         raise InvalidQueryError("$nor requires an array")
    +     if any(matches(document, child) for child in condition):
    +         return False
    ```

    Tests should show `{"$nor": [{"age": 10}, {"name": "Grace"}]}` accepts an
    Ada/20 document, rejects when one child matches, and raises for a document
    operand. Acceptance is a green targeted `tests/test_query.py` run in a
    disposable worktree or after manually applying and reverting the proposal.

### 4. Hands-on: expose cross-element matching

Without source edits, insert `{"_id": 1, "scores": [2, 20]}` and query
`{"scores": {"$gt": 10, "$lt": 5}}`. Acceptance: print the matching `_id` and
one sentence explaining why `$elemMatch` would express a different constraint.

??? note "Reference answer"

    MiniMongoDB returns document `1`: `20` satisfies `$gt` and `2` satisfies
    `$lt`. `$elemMatch` would require one array element to satisfy both, which
    no element can do; `$elemMatch` is not implemented here.

## Summary

Query semantics have one owner: `matches`. Dotted resolution may produce many
candidate values; scalar operands may expand stored arrays, while array and
document literals remain whole exact values. Operators then combine presence,
equality, or comparison rules, and logical operators recurse over queries.
Chapter 4 reuses both path traversal and matching, but changes the problem:
instead of deciding whether a document qualifies, it must construct a new
document atomically while preserving identity.
