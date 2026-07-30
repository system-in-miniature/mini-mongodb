# Chapter 9: Aggregation as a Document Pipeline

A query answers which documents match. An aggregation pipeline answers a
broader question: how should a stream of documents be filtered, reshaped,
combined, ordered, and bounded? MiniMongoDB implements five stages—
`$match`, `$project`, `$group`, `$sort`, and `$limit`—as small composable
operators. The key lesson is not the number of stages. It is where a stage can
stream and where semantics force it to materialize all input.

## Learning objectives

By the end of this chapter, you will be able to:

- trace `Collection.aggregate` through `execute_pipeline` and its stage
  dispatch;
- classify `$match`, `$project`, and `$limit` as streaming stages and
  `$group`/`$sort` as blocking stages;
- evaluate field references and nested expression shapes;
- explain group identity, accumulator initialization, and missing-value
  behavior; and
- identify which MongoDB aggregation capabilities and optimizations are
  intentionally absent.

## 9.1 A pipeline is staged iterable composition

`Collection.aggregate` in `src/minimongodb/collection.py` passes the
collection's document list to `execute_pipeline` in
`src/minimongodb/aggregate/__init__.py`. `execute_pipeline` first checks that
the pipeline is a list, then creates a generator that clones every source
document. Aggregation therefore does not leak internal mutable documents to
callers or mutate collection state.

Each stage must be a dictionary with exactly one operator. The dispatcher
validates stage-specific top-level shapes and replaces `stream` with the next
iterable:

```python
for stage in pipeline:
    operator, specification = next(iter(stage.items()))
    if operator == "$match":
        stream = _match(stream, specification)
    elif operator == "$project":
        stream = _project(stream, specification)
    ...
return list(stream)
```

Although the public result is ultimately an eager list, the intermediate value
is usually an iterable. That distinction allows an early `$match` to discard
documents before later work and allows `$limit` to stop pulling. Stage order is
observable: project away a field before matching it and the later match sees a
different document shape.

Composition also localizes responsibility. The dispatcher owns stage syntax,
each helper owns one transformation, and the terminal `list(stream)` owns
public materialization. A helper need not know whether its input came from the
collection, a matcher, or another projection. This is the same interface
advantage that makes iterator-based operator engines teachable.

Invalid structure fails explicitly with `InvalidPipelineError`: non-list
pipelines, stages containing two operators, unknown stage names, and invalid
stage specifications are not silently ignored.

## 9.2 Streaming stages

`_match` is a generator. It pulls one document, calls the existing
`query.matches`, and yields only accepted documents. This reuse is important:
array fan-out, exact embedded-document matching, dotted paths, and the supported
query operators do not acquire a second aggregation-specific interpretation.
However, `_match` receives the current pipeline iterable directly; it does not
call `Collection._run_query`, so there is no index planning or pushdown.

`_project` is also a generator. It first classifies fields whose expressions
are `0`/`False` as exclusions and the remainder as inclusions or computed
fields. Excluding fields other than `_id` cannot be mixed with inclusion or
computed expressions. In inclusion mode, `_id` is preserved by default, direct
`1`/`True` fields are read with `get_path`, and other expressions are evaluated
by `_evaluate`. In exclusion mode, it clones the whole document and calls
`unset_path` for each excluded field.

`_limit` validates a nonnegative integer and yields until its enumeration
position reaches the limit. It explicitly rejects Boolean values even though
`bool` is a Python subclass of `int`. At position `limit`, it breaks without
pulling the rest of the upstream iterable. Placing `$limit` before a blocking
stage can therefore bound that stage's input, though doing so changes the
pipeline's meaning.

These stages use Python generators, so they hold one current document plus
their small local state. “Streaming” does not mean network streaming or an
async cursor; it describes incremental consumption inside one synchronous
call.

## 9.3 Expression evaluation

Function `_evaluate` supports a compact expression language:

- a string beginning with `$` is a dotted field reference;
- the special string `$` refers to the whole document;
- dictionaries and lists are recursively evaluated as nested shapes; and
- every other value is a deep-copied constant.

A missing field reference returns the `MISSING` sentinel from `bson.path`.
Projection omits a missing direct field. Within a nested list, missing becomes
`None`; within a nested document, that child key is omitted. These conversions
ensure the internal sentinel never leaks into a returned BSON-shaped value.

This language is sufficient for projections such as
`{"name": "$item.name"}` and group keys such as `"$region"`, but it does not
implement MongoDB's arithmetic, conditional, date, string, array, or variable
expression families.

## 9.4 Why grouping blocks

`_group` cannot yield a final group when it sees the first member: a later
document might change the sum, average, minimum, maximum, or pushed list. It
therefore consumes the complete input into a `groups` dictionary keyed by
`canonical_key(group_value)`. Canonical keys let structured group identities
be hashable while preserving MiniMongoDB's BSON equality.

A missing group key becomes `None`. New groups initialize `$push` to an empty
list, `$min/$max` to a private `_UNSET` sentinel, and numeric accumulators to
`None`. The sentinel matters because BSON null is a real comparable value and
must not mean “no observation yet.”

Accumulator behavior is explicit:

- `$sum` adds numeric values and treats nonnumeric or missing values as zero;
- `$avg` tracks a separate `(total, count)` pair and ignores nonnumeric values;
- `$min` and `$max` compare present values with `bson_compare`;
- `$push` appends evaluated values, converting missing to `None`.

Function `_numeric` rejects Boolean despite Python's numeric inheritance. After
consumption, `_group` finalizes averages, empty sums, and never-seen min/max,
then returns `groups.values()`.

`_sort` is the other blocking stage. It calls `sorted` on the entire iterable
using a comparator that reads dotted paths and delegates mixed-type ordering to
`bson_compare`. Missing sort fields become `None`. Multiple sort fields are
checked in specification order, each with direction `1` or `-1`.

Thus the memory boundary is visible in source: `_match`, `_project`, and
`_limit` contain `yield`; `_group` owns dictionaries covering all groups, and
`_sort` calls `sorted`.

## 9.5 Compared with real MongoDB

MongoDB's aggregation framework has a large expression language and stages
such as `$unwind`, `$lookup`, `$facet`, `$setWindowFields`, `$merge`, and
`$out`. Its optimizer can reorder or combine stages, push eligible `$match`
work toward indexes, split pipelines across shards, and spill some blocking
work to disk subject to configuration and limits.

MiniMongoDB implements only `$match/$project/$group/$sort/$limit`. Its
`$group` supports `_id` plus `$sum/$avg/$min/$max/$push`. It runs in one
process against a cloned stable input sequence, with no optimizer, index
pushdown, spilling, parallelism, distributed merge, lookup, unwind, window
function, or output stage. `$group` and `$sort` may grow memory with all input.

See
[Differences: Aggregation differences](../DIFFERENCES.md#aggregation-differences)
and the `aggregate.execute_pipeline` row in
[MiniMongoDB ↔ MongoDB mapping](../mapping.md). The transferable model is
ordered operator composition, explicit expression evaluation, and
streaming-versus-blocking ownership—not production scalability.

## 9.6 Hands-on experiment: filter, group, and reshape

Run this exact command from the repository root:

```bash
UV_CACHE_DIR=/tmp/minimongodb-uv-cache uv run python - <<'PY'
import json
from minimongodb import Collection
sales = Collection("sales")
sales.insert_many([
    {"_id": 1, "region": "west", "amount": 3},
    {"_id": 2, "region": "east", "amount": 9},
    {"_id": 3, "region": "west", "amount": 7},
])
result = sales.aggregate([
    {"$match": {"region": "west"}},
    {"$group": {"_id": "$region", "total": {"$sum": "$amount"}, "avg": {"$avg": "$amount"}}},
    {"$project": {"_id": 0, "region": "$_id", "total": 1, "avg": 1}},
])
print(json.dumps(result, sort_keys=True))
PY
```

Measured output:

```text
[{"avg": 5.0, "region": "west", "total": 10}]
```

`$match` streams two west documents into the blocking `$group`; `$project`
then reshapes the one completed group. `sort_keys=True` normalizes only the
printed JSON key order so the measured output is reproducible; key order has
no role in the calculated totals.

Run the focused contract:

```bash
UV_CACHE_DIR=/tmp/minimongodb-uv-cache uv run pytest -q tests/test_aggregate.py
```

Measured output:

```text
........                                                                 [100%]
8 passed in 0.03s
```

Both commands use only the direct API; no socket is involved.

## 9.7 Exercises

### Understanding 1: moving a limit

Are `[$sort, $limit: 10]` and `[$limit: 10, $sort]` equivalent?

??? note "Reference answer"
    No. Sort-then-limit returns the first ten documents in global sorted order.
    Limit-then-sort consumes the first ten upstream documents and sorts only
    them. The second form bounds sort memory but changes semantics.

### Understanding 2: null versus no value

Why does `$min` initialize with `_UNSET` rather than `None`?

??? note "Reference answer"
    `None` is the BSON null value and participates in MiniMongoDB comparison
    order. Using it as “not initialized” would make a real null observation
    indistinguishable from no observation. `_UNSET` keeps those states separate.

### Hands-on 3: add `$count`

On a throwaway branch, add a blocking `$count` stage whose string
specification names the output field. It should emit one document such as
`{"matched": 3}`. Acceptance: test normal, empty-input, and invalid-name cases,
then run `uv run pytest -q tests/test_aggregate.py`.

??? note "Reference answer"
    A compact design adds dispatcher validation and a helper:

    ```diff
    +elif operator == "$count":
    +    stream = _count(stream, specification)

    +def _count(documents, field):
    +    if not isinstance(field, str) or not field or field.startswith("$"):
    +        raise InvalidPipelineError("$count requires an output field name")
    +    count = sum(1 for _ in documents)
    +    return [] if count == 0 else [{field: count}]
    ```

    Confirm the desired empty-input behavior against MongoDB before treating
    the exercise as compatibility work. The tutorial does not modify `src/`.

## Summary

MiniMongoDB composes aggregation as iterables: matching, projection, and limit
can consume incrementally, while grouping and sorting must own all relevant
input before returning final answers. Canonical BSON equality and comparison
remain shared across querying, indexing, and aggregation. Chapter 10 closes the
book by comparing these document mechanisms with relational schemas, joins,
plans, indexes, and transaction boundaries.
