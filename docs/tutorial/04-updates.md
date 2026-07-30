# Chapter 4: Update Operators

[中文版](../zh/tutorial/04-updates.md)

A query chooses a document; an update must transform it without leaving a
half-applied state, leaking caller-owned objects, changing `_id`, or publishing
indexes before durability. MiniMongoDB makes that sequence visible by building
a candidate copy first and swapping it into collection storage only after all
checks succeed.

## Learning objectives

By the end of this chapter, you will be able to:

- distinguish operator updates from replacement updates;
- trace `$set`, `$unset`, `$inc`, `$push`, and `$pull` through the source;
- explain copy-compute-validate-publish single-document atomicity;
- explain immutable `_id` and matched-versus-modified counts; and
- identify absent production features such as upsert and array filters.

## Two update languages, two public methods

`src/minimongodb/collection.py::Collection.update_one` and `update_many` accept
only operator documents. `Collection._update` rejects an empty update, a plain
replacement, or any mixture of top-level operator and ordinary keys. It tells
callers to use `replace_one` for replacement syntax.

That separation removes ambiguity. This is an operator update:

```python
{"$set": {"profile.city": "London"}, "$inc": {"visits": 1}}
```

This is a replacement:

```python
{"profile": {"city": "London"}, "visits": 1}
```

The first changes named paths and preserves all others. The second replaces the
entire document except for an omitted `_id`, which MiniMongoDB preserves.
`replace_one` rejects dollar-prefixed top-level keys so the two languages do
not silently cross.

For each stored document, `Collection._update` calls
`src/minimongodb/query/matcher.py::matches`. `update_one` stops after its first
match; `update_many` continues. `matched_count` counts qualifying documents,
while `modified_count` counts documents whose candidate is not BSON-equal to
the original. Setting a field to its current value matches but does not modify,
emit an oplog entry, or rebuild indexes.

## Compute on a private copy

`src/minimongodb/update/operators.py::apply_operator_update` starts with
`clone_document(original)`. Every operator mutates this private copy. If the
second of several operations fails, the stored original is still untouched.
After all operations, the function clones the candidate again. That second
boundary validates newly introduced nested values and disconnects mutable
objects borrowed from the user's update document.

The flow for a successful update is:

```text
match stored original
  -> clone original
  -> apply every requested path operation
  -> validate and clone candidate
  -> compare candidate with original
  -> validate every affected unique secondary index
  -> emit durable/logical mutation
  -> replace stored document and index entries
```

`Collection._replace_at` performs the final publication: it swaps the list
entry, replaces the `_id` map value, and asks each secondary index to replace
its old keys with new keys. With a durable `Database`, `Oplog.emit` first calls
the journal listener. Therefore a journal failure occurs before this
publication step. Chapter 5 follows that boundary into storage.

The model is atomic for one document in one Python process: no failed operator
leaves a partial candidate visible. It is not transactional isolation among
concurrent clients, and multi-document updates are not all-or-nothing.

## The five operators

`apply_operator_update` permits only names in `SUPPORTED_OPERATORS`.
`_mapping_operand` requires each operand to be a document mapping paths to
values.

### `$set` and `$unset`

`$set` delegates to `src/minimongodb/bson/path.py::set_path`. Missing
dictionary parents may be created, but arrays are neither invented nor
extended. Numeric array positions must exist.

`$unset` calls `unset_path`. Removing a dictionary field deletes its key.
Unsetting an existing list position writes `None` instead of shifting later
positions. Missing paths are no-ops.

### `$inc`

`$inc` obtains the current value with `get_path`. The amount must be a real
number but not a boolean. If the target is missing, the amount becomes its
initial value. If present, the target must also be numeric and nonboolean.
The function then stores `current + amount`.

Rejecting booleans is another place where database type semantics override
Python's `bool`-is-`int` inheritance. A failed numeric check raises
`InvalidUpdateError` while the private candidate is discarded.

### `$push`

`$push` appends one value to an existing list or creates a one-element list
when the field is missing. A present non-list target is an error. The miniature
does not implement MongoDB modifiers such as `$each`, `$slice`, `$sort`, or
`$position`.

### `$pull`

`$pull` requires an existing target to be a list. It removes elements for
which the normal matcher accepts a synthetic document:

```python
matches({"value": item}, {"value": value})
```

This reuse means `$pull: {"scores": {"$gt": 5}}` inherits the query subset's
comparison semantics. A missing target is a no-op; a non-list target fails.

## `_id` is immutable

Every operator path passes through
`src/minimongodb/update/operators.py::_guards_id`. It rejects `_id` and any
path beginning `_id.`. Removing, incrementing, or changing part of an identity
would invalidate the collection's unique identity map and the key used by
oplog replay.

`replacement_document` enforces the same invariant differently. It clones the
replacement, reads the old identity, and rejects a supplied unequal `_id`. If
the replacement omits `_id`, the function inserts the old value. The field may
appear later in insertion order in this teaching representation, which is why
the experiment's replaced document prints `status` before `_id`.

After a candidate is built, `Collection._update` asks every secondary index to
`validate_replace` before emitting or publishing. A unique-index conflict
therefore leaves the document, oplog, and all indexes unchanged.

## From action to post-image

The user's update expresses an action: increment, append, or remove. Directly
replaying such actions twice could change state twice. Before emitting an
update, `src/minimongodb/collection.py::Collection._post_image_update` reads
each requested path from the final candidate and rewrites it as `$set` or
`$unset`. An increment from two by three therefore enters the oplog as
`{"$set": {"count": 5}}`.

Chapter 6 develops this idempotence mechanism fully. At this point, notice the
separation: `apply_operator_update` implements user-requested transformation;
`_post_image_update` implements repeat-safe logging representation. The stored
document and the oplog do not need identical syntax to represent the same
accepted mutation.

## Compared with real MongoDB

Real MongoDB also separates replacement and operator-style updates, protects
immutable `_id`, and provides single-document atomicity. The local
`$set/$unset/$inc/$push/$pull` behaviors intentionally model a small useful
subset, including `$unset` preserving array positions.

MiniMongoDB has no upsert, positional `$`, `$[]`, filtered positional
operators, array filters, update pipelines, collation, write concern, sessions,
transactions, retryable writes, or find-and-modify variants. `$push` lacks all
modifiers. `$pull` reuses the local matcher and therefore inherits its
nonportable global type order and top-level extensions.

`update_many` and other batch operations commit documents one at a time. If
durable append fails for item N, earlier items stay visible and durable; item N
and later items do not publish. This is a committed-prefix contract, not a
multi-document transaction.

See [update and CRUD differences](../DIFFERENCES.md#update-and-crud-differences),
the `update.operators` mapping row, and the `collection.Collection` row in the
[mapping table](../mapping.md#minimongodb--mongodb-mapping).

## Hands-on experiment: operator versus replacement

Run:

```bash
UV_CACHE_DIR=/tmp/minimongodb-uv-cache uv run python - <<'PY'
from minimongodb import Collection
items = Collection("items")
items.insert_one({"_id": 1, "stats": {"count": 2}, "tags": ["db", "old"]})
result = items.update_one(
    {"_id": 1},
    {"$inc": {"stats.count": 3}, "$push": {"tags": "python"}, "$pull": {"tags": "old"}},
)
print("counts:", result.matched_count, result.modified_count)
print("updated:", items.find_one())
replacement = items.replace_one({"_id": 1}, {"status": "archived"})
print("replacement counts:", replacement.matched_count, replacement.modified_count)
print("replaced:", items.find_one())
PY
```

Measured output:

```text
counts: 1 1
updated: {'_id': 1, 'stats': {'count': 5}, 'tags': ['db', 'python']}
replacement counts: 1 1
replaced: {'status': 'archived', '_id': 1}
```

The operator update preserves unrelated structure and changes named paths.
The replacement removes the old structure and preserves only the immutable
identity. This direct-API experiment does not validate sockets or drivers.

## Exercises

### 1. Understanding: matched but unmodified

What counts should result from two documents with `x=1` followed by
`update_many({"x": 1}, {"$set": {"x": 1}}`?

??? note "Reference answer"

    `matched_count` is 2 and `modified_count` is 0. Both documents satisfy the
    query, but each candidate is BSON-equal to its original, so no update oplog
    entry or index replacement is needed.

### 2. Understanding: failure atomicity

An update contains a valid `$set` followed by `$inc` on a string. Why does the
valid first change remain invisible?

??? note "Reference answer"

    Operators mutate a private clone returned only after every operation and
    validation succeeds. The bad `$inc` raises before `Collection._update`
    emits or calls `_replace_at`, so the stored original is unchanged.

### 3. Hands-on: propose `$rename`

Draft, but do not apply, a diff for a `$rename` operator. Acceptance: guard
both source and destination against `_id`, reject overlapping/invalid paths,
move a missing source as a no-op, preserve copy-first atomicity, and propose
tests for nested paths and rollback after failure.

??? note "Reference answer"

    A complete design adds `$rename` to `SUPPORTED_OPERATORS`, requires a
    string destination, runs `_guards_id` on both paths, reads the source with
    `get_path`, and if present performs `set_path(destination, value)` before
    `unset_path(source)` on the private candidate. It must define and reject
    source/destination ancestor overlap to avoid self-destruction. Tests should
    include a nested success, missing source, immutable identity, invalid
    destination, overlap, and a multi-operator failure leaving storage intact.

### 4. Hands-on: verify caller-value isolation

Set a field to a nested caller-owned dictionary, mutate that dictionary after
`update_one`, and read the document again. Acceptance: stored nested content
must retain the pre-mutation value.

??? note "Reference answer"

    Pass `value = {"items": [1]}` through `$set`, then append `2` to
    `value["items"]`. The stored result must remain `{"items": [1]}` because
    `apply_operator_update` performs its final validating clone.

## Summary

MiniMongoDB cleanly separates operator updates from replacements. It computes
on a private copy, validates values and indexes, emits the accepted mutation,
and only then replaces stored state. Five operators share dotted-path
mechanics; immutable `_id` protects identity and replay. Chapter 5 gives the
word “accepted” a crash boundary: when a collection belongs to `Database`,
the emitted mutation must reach an fsynced journal frame before memory and
indexes can publish it.
