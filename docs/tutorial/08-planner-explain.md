# Chapter 8: Planning a Query and Reading `explain`

Creating an index does not imply that every matching query should use it. A
planner must first prove that the index can preserve matcher semantics, then
decide whether its candidate set is better than scanning the collection.
MiniMongoDB makes both choices deterministic and exposes the result with
MongoDB-shaped `IXSCAN`/`COLLSCAN` vocabulary.

## Learning objectives

By the end of this chapter, you will be able to:

- follow `Collection.explain` through `Collection._run_query` and
  `choose_plan`;
- derive which fields of a compound index form a usable prefix;
- explain the candidate-count cost model and its deterministic tie breaks;
- distinguish `keysExamined`, `docsExamined`, and `nReturned`; and
- identify correctness fallbacks for multikey predicates and root-array
  `_id` values.

## 8.1 Planning does not replace matching

The public entry point is `Collection.explain` in
`src/minimongodb/collection.py`. It normalizes `None` to `{}`, calls
`Collection._run_query`, then packages the selected plan and actual execution
counters:

```python
return {
    "queryPlanner": {"winningPlan": plan.summary(normalized)},
    "executionStats": {
        "nReturned": len(documents),
        "keysExamined": keys_examined,
        "docsExamined": docs_examined,
    },
}
```

`find`, `find_one`, and `count_documents` use the same `_run_query`; explain is
not a separate simulation. Before choosing a plan, `_run_query` calls
`matches({}, normalized)`. This apparently odd empty-document match validates
query syntax even when the collection is empty or an index would produce zero
candidates.

The plan provides only a candidate source. When it is a collection scan,
`candidates` is the insertion-ordered document list. When it is an index scan,
the plan provides canonical document ids. Because index ownership buckets are
sets, `_run_query` walks the original storage list and retains documents whose
ids are in that set. It then calls `matches` on every candidate.

Two invariants follow. First, using an index must not change query semantics:
the matcher remains the final authority. Second, using an index must not change
the public result order: `find` still returns an eager list in insertion order.
The index narrows work; it does not define result order.

## 8.2 The plan object

`src/minimongodb/plan/__init__.py` defines frozen dataclass `Plan`. Its
essential fields are `stage`, optional `index`, `prefix_length`,
`candidate_ids`, and `keys_examined`. `Plan.summary` returns
`{"stage": "COLLSCAN"}` when there is no index. For a secondary index it adds
the index name, complete key pattern, and bounds for the usable prefix.

The automatic `_id_` index does not have a `SecondaryIndex` instance, so
`choose_plan` builds a `summary_override`. Exact `_id`, `$eq`, and `$in`
lookups can map values directly through `IdIndex.get`. The resulting plan
reports the familiar name `_id_`, key pattern `{"_id": 1}`, and query bound.

The `Plan` contains candidate ids rather than candidate documents. This keeps
planning concerned with identity and cost while `Collection` owns storage
order, cloning, and final matching.

## 8.3 A deliberately small cost model

Function `choose_plan` asks every secondary index for
`SecondaryIndex.prefix_length(query)`. An index with no usable leftmost prefix
is ignored. Each usable index then runs `SecondaryIndex.scan`, which returns
the candidate owner set and the count of matching distinct index keys examined.

Candidates are ranked by a tuple:

1. fewer candidate document owners;
2. longer usable compound prefix, represented as negative length; and
3. lexicographically smaller index name.

These tie breaks make the same state and query choose the same plan every time.
There is no random trial execution or time-dependent sampling. After selecting
the best index, the planner still compares its candidate count with the full
collection count. When the estimate is greater than or equal to the number of
documents, it returns `COLLSCAN`. An unselective index therefore loses even
though it is technically usable.

This estimate is exact for the miniature's current in-memory ownership sets,
but it is not a production cost model. It knows nothing about disk pages,
cache residency, index height, fetch cost, CPU, sort satisfaction, projections,
or historical statistics. Its purpose is to reveal the decision boundary:
semantic eligibility first, estimated reduction second.

Plan choice can change as data changes even when query and index definitions
do not. If `kind == "rare"` grows from one owner to every owner, the same
`kind_1` index moves from a winning `IXSCAN` to `COLLSCAN`. That is expected:
the planner derives candidate cardinality from current ownership buckets.
Determinism means identical state produces an identical decision, not that a
query is permanently attached to one stage. Since there is no plan cache, each
call recomputes this small choice.

## 8.4 Reading the three counters

`nReturned` is the number of candidates that pass the full matcher.
`docsExamined` is the number of candidate documents passed to the matcher.
`keysExamined` is the number of matching distinct index-key buckets visited by
the index scan. A collection scan reports zero keys because no index is read.

For four documents where only one has `kind == "rare"`:

- before an index, `COLLSCAN` has `keysExamined=0`,
  `docsExamined=4`, and `nReturned=1`;
- after a selective `kind_1` index, `IXSCAN` has
  `keysExamined=1`, `docsExamined=1`, and `nReturned=1`.

Do not assume `keysExamined == docsExamined`. One key bucket may own multiple
documents, and a compound or range scan may inspect several keys. Also do not
treat `nReturned/docsExamined` as a complete cost estimate; it is an observable
teaching ratio, not latency.

## 8.5 Correctness-driven fallbacks

The planner contains two unusually instructive escape hatches.

First, MiniMongoDB permits a root array as `_id`, even though this is not a
portable MongoDB identity design. The matcher allows scalar predicates to fan
out through stored arrays. A direct canonical lookup for scalar `1` would not
find stored `_id: [1, 2]`, although the matcher says it matches. `IdIndex`
property `has_root_array` detects this collection state. Functions
`_id_lookup_values` and `_id_lookup_is_safe_with_array_ids` allow whole-array
lookups but force scalar equality and scalar `$in` back to `COLLSCAN`.

Second, a multikey index stores individual leaves, while the matcher may let
different array elements satisfy different operators when there is no
`$elemMatch`. For document `{"values": [1, 20]}`, query
`{"values": {"$gt": 10, "$lt": 5}}` is accepted because different elements
satisfy the two comparisons. Intersecting both conditions against a single
leaf key would wrongly discard it. `SecondaryIndex.prefix_length` therefore
returns no usable prefix for this unsafe shape, and the planner scans the
collection.

These fallbacks express a central rule: a slower complete plan is better than a
fast incomplete plan.

## 8.6 Compared with real MongoDB

MongoDB's query planner considers many candidate plan trees and can use
statistics, cached plans, trial execution, index intersection, covered queries,
sort satisfaction, and many stage types. Real `explain()` has verbosity modes
and can report rejected plans, execution time, works, yields, and storage
metrics. It is a cursor operation in normal driver usage.

MiniMongoDB exposes `Collection.explain(query)` eagerly. It returns one winning
`IXSCAN` or `COLLSCAN` and three counts. There is no statistics catalog,
histogram, plan cache, intersection, covered query, optimizer, timing, or
rejected-plan list. Secondary indexes are in-memory maps rather than B-trees.
`$match` inside aggregation is not pushed down to this planner.

The full contract is in
[Differences: Index and planner differences](../DIFFERENCES.md#index-and-planner-differences)
and the `plan.choose_plan` row of
[MiniMongoDB ↔ MongoDB mapping](../mapping.md). Preserve the ideas of semantic
eligibility, selective access, candidate filtering, and observed work; do not
infer production plan quality from this tiny estimator.

## 8.7 Hands-on experiment: make the winning plan change

Run:

```bash
UV_CACHE_DIR=/tmp/minimongodb-uv-cache uv run python labs/lab_explain.py
```

Measured output:

```text
before index: COLLSCAN
docs examined: 4
after index: IXSCAN
docs examined: 1
```

The query and answer are unchanged. Only the candidate source and amount of
matcher work change. Now run the focused planner contract:

```bash
UV_CACHE_DIR=/tmp/minimongodb-uv-cache uv run pytest -q tests/test_planner.py
```

Measured output:

```text
......                                                                   [100%]
6 passed in 0.05s
```

This suite includes compound-prefix, unselective-index, automatic `_id_`, and
multikey correctness fallbacks. It uses the direct API, not a socket.

## 8.8 Exercises

### Understanding 1: an index that loses

A collection has 100 documents, and the best usable index produces 100
candidate owners. Which stage wins, and why?

??? note "Reference answer"
    `COLLSCAN` wins. In `choose_plan`, an index is chosen only when its
    candidate estimate is strictly less than `document_count`. Equal work does
    not justify the extra index path in this model.

### Understanding 2: compound prefix

Given index `{tenant: 1, created: 1, kind: 1}`, what prefix is usable for query
`{tenant: "a", created: {"$gte": 10}, kind: "error"}`?

??? note "Reference answer"
    The usable prefix has length two: equality on `tenant`, then the range on
    `created`. Prefix growth stops after a range predicate, so `kind` is not an
    index bound. The matcher still checks the complete query.

### Hands-on 3: expose the prefix length

On a throwaway branch, add `prefixLength` to secondary `IXSCAN` summaries.
Acceptance: an explain test for `{tenant: "a", kind: "rare"}` against
`tenant_1_kind_1` asserts `prefixLength == 2`, while existing summary tests are
updated intentionally; run `uv run pytest -q tests/test_planner.py`.

??? note "Reference answer"
    Extend only `Plan.summary`:

    ```diff
     return {
         "stage": "IXSCAN",
         "indexName": self.index.name,
         "keyPattern": self.index.key_pattern,
         "indexBounds": {...},
    +    "prefixLength": self.prefix_length,
     }
    ```

    Decide separately whether the `_id_` summary should report `1` and test
    that contract. No source change is applied by this tutorial.

## Summary

MiniMongoDB validates query syntax, proves index eligibility, ranks usable
indexes by candidate ownership with deterministic tie breaks, and lets the
matcher remain the final authority. `explain` reports the chosen candidate
source and actual key/document/result counts. Chapter 9 shifts from choosing a
source to composing transformations: documents will flow through streaming
and blocking aggregation stages.
