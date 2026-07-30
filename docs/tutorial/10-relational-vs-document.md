# Chapter 10: Relational and Document Systems

The final chapter changes perspective. Instead of adding another mechanism, we
will ask the same engineering questions of a relational miniature and this
document miniature: What is stored? How are names bound? Where does matching
happen? What does an index own? Which operators block? What is the atomicity
boundary? The goal is not to declare one model superior. It is to learn which
assumptions may safely transfer and which must be re-derived.

## Learning objectives

By the end of this chapter, you will be able to:

- compare schema-bound rows with self-shaped nested documents;
- relate SQL binding and relational plan operators to dotted-path matching and
  document pipeline stages;
- contrast primary/unique indexes with MiniMongoDB's mandatory `_id` and
  multikey ownership;
- state MiniMongoDB's actual single-document and batch durability boundaries;
  and
- use the repository mapping and differences ledger to separate transferable
  mechanisms from teaching simplifications.

## 10.1 Storage model: shape before operators

A relational system stores tuples under a declared relation schema. Column
names, types, nullability, and constraints have catalog meaning before a query
examines a row. A document system stores records that carry their own nested
shape. Two documents in one collection may have different fields or array
lengths, so path resolution and missing values remain runtime concerns.

MiniMongoDB makes this concrete in
`src/minimongodb/bson/types.py`. Function `clone_document` validates and
deep-copies supported Python `dict`/`list` trees. Functions `type_tag`,
`bson_equal`, `canonical_key`, and `bson_compare` establish value identity and
order without a collection schema. In `src/minimongodb/bson/path.py`,
`get_path` interprets dotted components dynamically, traversing dictionaries
and explicit array positions and returning `MISSING` when a path does not
exist.

The relational analogue is a bound column reference: after parsing and binding,
an operator knows which tuple slot and declared type it reads. MiniMongoDB's
`"customer.address.city"` remains a value-level path evaluated against each
document. This flexibility is useful for evolving nested shapes, but it moves
some failures and ambiguities from definition time to query/update time.

Identity differs too. Relational tables may declare a primary key and additional
unique constraints. Every MiniMongoDB `Collection` constructs `IdIndex` in
`Collection.__init__`; missing `_id` values are filled by its injected
generator in `Collection.insert_many`. The automatic index is mandatory, but
the miniature even permits structured `_id` values, which requires canonical
BSON-shaped keys rather than a scalar tuple column.

## 10.2 Query language and operator flow

The relational path commonly reads:

```text
SQL text → parser → binder/catalog → logical plan → physical operators
```

Predicates consume schema-bound expressions, and a Volcano-style executor lets
parent operators pull tuples from children. Selection, projection, join,
aggregate, and sort form a plan tree.

MiniMongoDB begins after parsing because its API already receives a Python
query document. `Collection._run_query` in
`src/minimongodb/collection.py` validates that document with `matches`,
calls `choose_plan`, obtains either all documents or indexed candidate ids,
then applies `matches` as the final filter. Its flow is:

```text
query dict → IXSCAN/COLLSCAN candidate choice → matcher → cloned result list
```

This shorter front end does not mean the semantics are trivial. Function
`matches` in `src/minimongodb/query/matcher.py` owns array element fan-out,
literal whole-array/document equality, dotted selection, missing/null
distinction, and the supported logical/comparison operators. Those runtime
value rules are the document counterpart to relational binding and
three-valued predicate semantics.

Aggregation adds an operator pipeline. `execute_pipeline` in
`src/minimongodb/aggregate/__init__.py` composes document iterables.
`$match/$project/$limit` pull incrementally; `$sort/$group` block and
materialize. Relational `Filter`/`Project` operators and document
`$match/$project` share the idea of per-record transformations. Relational
`Sort`/`Aggregate` and document `$sort/$group` share the memory boundary. The
record being transformed differs: a fixed tuple with bound columns versus a
self-shaped nested document with dotted references.

MiniMongoDB has no join stage. A relational normalized design might store
orders and line items in separate tables and join them. A document design can
embed line-item subdocuments so one order is read as a unit, at the cost of
duplication and potentially larger update units. Real MongoDB offers
`$lookup`; this miniature does not.

## 10.3 Indexes: row keys versus document fan-out

Both models use indexes to map ordered keys to record identities and both rely
on a leftmost prefix for ordered compound keys. MiniMongoDB's
`SecondaryIndex.prefix_length` and `choose_plan` make that common mechanism
visible.

The document model adds multikey ownership. Function
`SecondaryIndex._document_entries` in
`src/minimongodb/index/secondary.py` walks dotted paths, recursively expands
array leaves, and computes compound Cartesian products. One document can
therefore own many index keys. A conventional scalar relational index normally
gets one key tuple per row; representing tags relationally would usually mean a
child table with one row and index entry per tag.

That distinction changes cardinality reasoning. In MiniMongoDB,
`keysExamined` counts matching key buckets and `docsExamined` counts candidate
owners. Several keys can point to one document and one key can point to several
documents. In a normalized child table, the planner instead reasons about child
rows and a join back to the parent.

Uniqueness remains prospective in both worlds: reject conflicting keys before
publishing state. MiniMongoDB implements this in
`SecondaryIndex.validate_documents` and `validate_replace`. Yet its missing
field rule is specific: missing occupies a null-like key, so a unique index
allows one missing/null owner. Do not transfer that result to SQL `NULL`
uniqueness rules or to every MongoDB index option without checking the target
system.

## 10.4 Updates, logs, and transaction boundaries

Relational systems typically expose transactions spanning multiple statements
and rows, with isolation and rollback rules. Their write-ahead log records
storage changes needed for crash recovery; a production database may also
expose logical decoding or replication records.

MiniMongoDB's boundary is smaller. `Collection._update` constructs and
validates a copy, durably emits one post-image oplog entry, then swaps the
document and its indexes with `Collection._replace_at`. A single-document
mutation is atomic only inside one Python process. There is no concurrent
reader/writer isolation, MVCC, session, read/write concern, or multi-document
transaction.

Batch methods do not enlarge that boundary. `insert_many` validates candidates
as a batch but emits and publishes one document at a time. `update_many` and
`delete_many` likewise commit per document. A journal failure leaves an earlier
durable prefix visible and later items untouched. This differs sharply from
wrapping a relational multi-row statement in one ACID transaction.

The log design also differs. `Collection._post_image_update` rewrites actions
such as `$inc` into final `$set` values. `Oplog.emit` sends that logical record
to the journal listener before publishing its sequence. Real MongoDB separates
WiredTiger recovery journal machinery from replica-set oplog machinery;
MiniMongoDB deliberately frames the same logical entry for local recovery.

`Database.__init__` in `src/minimongodb/database.py` loads checkpoint and
journal state, restores documents/index definitions, and calls `replay` only
after the checkpoint sequence. `Database.checkpoint` writes the complete
database snapshot and current durable sequence. This resembles the broad
snapshot-plus-newer-log recovery shape used across systems, but not a
page-oriented relational WAL or WiredTiger checkpoint implementation.

## 10.5 A practical comparison matrix

| Question | Relational miniature / MiniPostgres lens | MiniMongoDB |
|---|---|---|
| Stored unit | Schema-typed row in a relation | Self-shaped nested document |
| Name resolution | Bound table/column reference | Runtime dotted path |
| Query surface | Parsed SQL expressions | Python query document / MQL subset |
| Physical access | Scan operators over rows/indexes | `COLLSCAN` or `IXSCAN` candidates |
| Composition | Plan tree; parent pulls tuples | Ordered document stage pipeline |
| Repetition | Child table produces more rows | Array produces multikey fan-out |
| Identity | Declared PK/UNIQUE | Mandatory automatic `_id_` |
| Blocking work | Sort and aggregate own input | `$sort` and `$group` own input |
| Update unit | Governed by transaction | One copied document per durable entry |
| Recovery log | WAL shaped for relational storage | Framed logical post-image entries |

This matrix is a reading guide, not a compatibility claim. Use it to ask the
same ownership questions: Who validates a value? Who chooses candidates? Who
owns intermediate state? When is a change durable? What can be retried?

## 10.6 Compared with real systems

Real PostgreSQL-family systems add catalogs, SQL parsing/binding, joins,
constraints, sophisticated optimizers, MVCC, locks, transaction isolation,
page storage, WAL, vacuum, replication, and far more. Real MongoDB adds binary
BSON, wire protocol and drivers, storage-engine pages/cache/checkpoints,
replica sets, sharding, transactions, concerns, rich MQL/aggregation, and many
index types.

MiniMongoDB is a deterministic single-process kernel, not a server. It has no
wire protocol, authentication, concurrent isolation, multi-document ACID,
replication, sharding, `$lookup`, or complete BSON/MQL. Its strongest lessons
are local: BSON-shaped equality, path/array matching, canonical multikey
ownership, candidate planning, post-image convergence, and durability-before-
publication.

Consult [Differences from MongoDB](../DIFFERENCES.md) before generalizing any
behavior. Then use
[Relation operators versus document pipelines](../mapping.md#relation-operators-versus-document-pipelines)
and the level labels in [the mapping table](../mapping.md): “Equivalent” names
an invariant, “Intentionally simplified” narrows machinery, and “Semantically
opposite” warns against analogy. This evidence discipline is the method the
System-in-Miniature series is designed to teach.

## 10.7 Hands-on experiment: read one embedded shape three ways

Run:

```bash
UV_CACHE_DIR=/tmp/minimongodb-uv-cache uv run python - <<'PY'
from minimongodb import Collection
orders = Collection("orders")
orders.insert_many([
    {"_id": 1, "customer": {"name": "Ada"}, "items": [{"sku": "PEN"}, {"sku": "BOOK"}], "total": 12},
    {"_id": 2, "customer": {"name": "Lin"}, "items": [{"sku": "PEN"}], "total": 4},
])
print("dotted query:", [d["_id"] for d in orders.find({"customer.name": "Ada"})])
print("array fan-out:", [d["_id"] for d in orders.find({"items.sku": "PEN"})])
print("grouped:", orders.aggregate([{"$group": {"_id": None, "revenue": {"$sum": "$total"}}}]))
PY
```

Measured output:

```text
dotted query: [1]
array fan-out: [1, 2]
grouped: [{'_id': None, 'revenue': 16}]
```

A relational representation would commonly separate orders and items, bind
columns through schemas, and use a join or aggregate over rows. The output does
not prove either layout better; it makes the embedded document's runtime path
and array semantics visible.

Run the cross-mechanism contract:

```bash
UV_CACHE_DIR=/tmp/minimongodb-uv-cache uv run pytest -q tests/test_query.py tests/test_aggregate.py tests/test_indexes.py
```

Measured output:

```text
................................                                         [100%]
32 passed in 0.13s
```

These commands use no socket. They verify MiniMongoDB behavior only; comparing
against a live PostgreSQL or MongoDB service would require runtime verification
and is not claimed here.

## 10.8 Exercises

### Understanding 1: modeling tags

Compare an embedded `tags` array with a relational `article_tags` child table.
Where does repetition live, and what does an index entry identify?

??? note "Reference answer"
    In the document model, repetition lives inside one document and a multikey
    index maps each expanded tag key back to the same document `_id`. In the
    normalized relational model, repetition lives in separate child rows; an
    index identifies those rows, and reaching the article may require a join.

### Understanding 2: atomicity claim

Can a successful validation pass in `insert_many` be described as a
multi-document transaction?

??? note "Reference answer"
    No. Validation is batch-wide, but durable emit and publication happen one
    document at a time. A failure keeps the committed prefix. There is no
    rollback, isolation, or multi-document ACID boundary.

### Hands-on 3: model a relational projection

Without changing `src/`, write a temporary script that turns the embedded
orders from the experiment into flat `(order_id, customer_name, sku)` tuples.
Acceptance: the output has three tuples in deterministic order and preserves
two rows for order 1.

??? note "Reference answer"
    One direct-API solution is:

    ```python
    rows = [
        (order["_id"], order["customer"]["name"], item["sku"])
        for order in orders.find()
        for item in order["items"]
    ]
    assert rows == [
        (1, "Ada", "PEN"),
        (1, "Ada", "BOOK"),
        (2, "Lin", "PEN"),
    ]
    ```

    The comprehension performs an application-side analogue of unnesting.
    Real relational execution and MongoDB `$unwind` have richer planning and
    semantics; the acceptance checks only the shape transformation.

## Summary

Relational and document systems share deep mechanisms—typed identity, candidate
access, operator composition, blocking state, uniqueness, durable logs—but
place them around different record shapes and atomicity contracts.
MiniMongoDB's value is that every boundary can be followed from a Python
document through matching, indexing, planning, post-image logging, and
recovery. The durable habit to take to real systems is to inspect ownership and
evidence before transferring an analogy.
