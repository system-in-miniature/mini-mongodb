# Chapter 7: Secondary Indexes and Multikey Expansion

An index is not merely a faster dictionary lookup. It is a second
representation of collection state, with its own equality rules, ordering,
uniqueness constraints, and publication timing. If any one of those rules
disagrees with the document matcher, an index can make a correct query return
the wrong answer. MiniMongoDB keeps the machinery small enough to inspect while
preserving these correctness boundaries.

## Learning objectives

By the end of this chapter, you will be able to:

- normalize single-field and compound index specifications and explain the
  ascending-only restriction;
- trace a dotted field through array traversal, multikey expansion, and
  BSON-tagged canonicalization;
- explain why duplicate keys from one document are removed before uniqueness
  checks;
- predict when a compound index has a usable leftmost prefix; and
- show why index validation, durable logging, and index publication must occur
  in that order.

## 7.1 One value needs two representations

The core implementation is
`src/minimongodb/index/secondary.py`, class `SecondaryIndex`. It maintains two
dictionaries. `_values` preserves the original BSON-shaped tuple for ordered
comparison; `_owners` maps the canonical compound key to the set of document
identities that own it.

Why not use the Python value directly as a dictionary key? Documents and arrays
are unhashable, and Python considers `True == 1`. MiniMongoDB's BSON contract
requires Boolean and number identities to remain distinct, while numerically
equal integers and floats compare equal. Function `canonical_key` in
`src/minimongodb/bson/types.py` recursively adds type tags and hashable
structure. Both `IdIndex` and `SecondaryIndex` use it, so identity,
uniqueness, and query buckets share one equality model.

Ordering is a different job. `SecondaryIndex._sort_token` wraps original
values in `_CompoundSort`; `_CompoundSort.__lt__` calls `bson_compare` field by
field. This follows MiniMongoDB's documented teaching order rather than
Python's incomparable mixed types. Storing canonical identity and original
ordered values separately prevents a convenient hash representation from
silently becoming the sorting semantics.

At the API boundary, `normalize_index_spec` accepts a field string, a mapping,
or ordered `(field, direction)` pairs. It rejects an empty pattern, repeated
fields, empty names, and every direction except `1`. `default_index_name`
joins the normalized components, so `[("team", 1), ("profile.city", 1)]`
becomes `team_1_profile.city_1`.

## 7.2 From a dotted path to multikey entries

Index extraction starts in `SecondaryIndex._document_entries`. For every
indexed field it calls `_field_values`, then computes the Cartesian product of
the field value lists. Each product tuple becomes one compound index entry.

The path walk in `_resolve_index_path` has three important cases:

1. A dictionary consumes the next path component.
2. A list plus a numeric component selects that explicit array position.
3. A list plus a nonnumeric component applies the still-unconsumed path to
   every element and concatenates the results.

After path resolution, `_leaves` recursively flattens arrays. Therefore
`{"tags": ["database", "python"]}` contributes two keys to an index on
`tags`, and `{"items": [{"sku": "A"}, {"sku": "B"}]}` contributes `A` and
`B` to an index on `items.sku`. A missing field contributes the null-like key
`None`, matching the project's non-sparse design.

The Cartesian product matters for compound indexes. If `tags` yields two
values and `regions` yields three, the document owns six compound keys.
MiniMongoDB intentionally allows this even when multiple indexed fields are
arrays. Real MongoDB rejects a compound multikey index when more than one
indexed field is an array in one document.

Before returning entries, `_document_entries` canonicalizes each tuple and
deduplicates it in a dictionary. Thus `["database", "database"]` makes the
index multikey but gives that document only one `database` entry. Without
deduplication, one document could conflict with itself in a unique multikey
index and scan counts would depend on repeated array elements rather than
ownership.

`SecondaryIndex.add` sets the sticky `is_multikey` flag when extraction
traverses or expands an array. It then adds the canonical `_id` to each
ownership bucket. `remove` deletes ownership and removes empty buckets;
`replace` performs both operations. The public
`Collection.index_information` reports key pattern, uniqueness, multikey
status, and distinct key-bucket count without exposing these internal maps.

## 7.3 Uniqueness is prospective validation

For a unique index, failure must occur before any conflicting state becomes
visible. `SecondaryIndex.validate_documents` copies current ownership sets and
simulates adding a whole prospective batch. It subtracts the candidate's own
document identity before deciding whether another owner conflicts.
`validate_replace` similarly permits a document to keep its existing key while
rejecting ownership by another document.

`Collection.create_index` in `src/minimongodb/collection.py` demonstrates the
complete build order:

1. normalize the specification and check a same-name definition;
2. construct an unpublished `SecondaryIndex`;
3. validate all existing documents and build its entries;
4. emit a durable `create_index` oplog entry; and
5. only then publish it in `self._indexes`.

If validation or journal append fails, the collection has no partially visible
index. Later inserts validate the entire candidate batch against all secondary
indexes, then commit one document at a time. Updates validate the candidate
against every index before emitting their post-image. After `Oplog.emit`
succeeds, `_replace_at` swaps the document, updates `_id`, and calls
`SecondaryIndex.replace`.

Index definitions survive restart by two paths. They are oplog operations, so
journal replay invokes `Collection._restore_index`. They are also included in
the database checkpoint through `Collection._index_definitions`; recovery
rebuilds entries from checkpointed documents instead of serializing internal
buckets. The test
`test_index_definition_survives_journal_and_checkpoint_recovery` verifies both
paths.

## 7.4 Prefixes and candidate ownership

Compound key order constrains useful searches. In
`SecondaryIndex.prefix_length`, scanning stops at the first absent indexed
field and stops after a range predicate. Equality and `$in` can continue a
prefix; `$gt/$gte/$lt/$lte` may close it. Unsupported operators produce no
usable prefix.

For index `{tenant: 1, kind: 1}`, query `{tenant: "a", kind: "rare"}` can use
both components. Query `{kind: "rare"}` cannot jump over `tenant`, so the
index is unusable. This is the same leftmost-prefix mental model used by
ordered compound indexes in production systems.

Multikey correctness adds stricter fallbacks. Without `$elemMatch`, separate
conditions may be satisfied by different array elements. Intersecting leaf-key
bounds could discard a document that the matcher accepts. Consequently
`prefix_length` refuses unsafe multi-operator or literal-array bounds on a
multikey index. Chapter 8 follows this decision into plan selection and
`explain`.

## 7.5 Compared with real MongoDB

MongoDB implements indexes using production storage-engine structures,
supports ascending and descending keys, and offers sparse, partial, wildcard,
hashed, text, geospatial, TTL, and other index families. It tracks multikey
path metadata, integrates indexes with concurrency and recovery, and has rules
for array-bound compounding that are richer than this model.

MiniMongoDB uses an in-memory ordered canonical map, permits only ascending
secondary/compound indexes, and supports dotted paths, unique constraints, and
multikey fan-out. Missing fields occupy a null-like key; because there is no
sparse option, a unique index permits only one missing/null owner. Its compound
Cartesian product for multiple array fields is explicitly more permissive than
MongoDB. Index buckets are owner sets, not B-tree pages.

Read the exact declarations in
[Differences: Index and planner differences](../DIFFERENCES.md#index-and-planner-differences)
and the `index.SecondaryIndex` row in
[MiniMongoDB ↔ MongoDB mapping](../mapping.md). The transferable invariants
are canonical equality, multikey ownership, leftmost prefixes, prospective
uniqueness checks, and atomic publication—not the data structure or complete
feature surface.

## 7.6 Hands-on experiment: observe one-to-many ownership

Run:

```bash
UV_CACHE_DIR=/tmp/minimongodb-uv-cache uv run python labs/lab_multikey_index.py
```

Measured output:

```text
one document can contribute several multikey index entries
index keys: 4 multikey: True
matched document ids: [1, 2]
```

The three documents contain five array elements, but only four distinct key
buckets: `database` is shared by documents 1 and 2. “Entries” therefore means
distinct canonical index keys, not number of documents or raw array elements.

Run the focused suite:

```bash
UV_CACHE_DIR=/tmp/minimongodb-uv-cache uv run pytest -q tests/test_indexes.py
```

Measured output:

```text
.........                                                                [100%]
9 passed in 0.16s
```

These direct-API experiments use no socket and were run in this repository.

## 7.7 Exercises

### Understanding 1: repeated array elements

For a non-unique index on `tags`, how many owned keys does
`{"_id": 1, "tags": ["db", "db", "python"]}` contribute? Is the index
multikey?

??? note "Reference answer"
    It contributes two keys, `db` and `python`, because
    `SecondaryIndex._document_entries` deduplicates canonical compound keys per
    document. `is_multikey` is still true because extraction expanded an
    array; multikey describes the path shape, not duplicate count.

### Understanding 2: missing values and unique indexes

Why can only one document with a missing `email` field exist under a unique
index on `email`?

??? note "Reference answer"
    `_field_values` maps a missing indexed field to `[None]`. With no sparse
    index option, missing and explicit null occupy the same canonical bucket,
    and uniqueness allows only one document owner for that bucket.

### Hands-on 3: report owned key count

On a throwaway branch, add a read-only `owned_keys(document)` teaching method
to `SecondaryIndex` that returns the number of deduplicated keys the document
would own. Acceptance: test a repeated two-value array and a two-field
2-by-3 compound product, expecting `2` and `6`; run
`uv run pytest -q tests/test_indexes.py`.

??? note "Reference answer"
    The implementation can delegate without exposing private maps:

    ```diff
    +def owned_keys(self, document: dict[str, Any]) -> int:
    +    return len(self.document_keys(document))
    ```

    Test through a constructed `SecondaryIndex` or a deliberately added public
    collection teaching API. Do not count raw leaves. This tutorial leaves
    `src/` unchanged.

## Summary

A secondary index is a synchronized, canonical view of document state.
MiniMongoDB separates equality keys from ordering values, expands dotted array
paths into deduplicated ownership buckets, validates uniqueness prospectively,
and publishes both definitions and mutations only after durable acceptance.
Chapter 8 uses those buckets as candidate estimates and asks the next question:
when is an available index actually cheaper and semantically safe to use?
