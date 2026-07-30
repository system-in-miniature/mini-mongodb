> **Language**: English | [简体中文](zh/DIFFERENCES.md)

# Differences from MongoDB

MiniMongoDB is a mechanism model, not a compatibility implementation. This
file records both the design's non-goals and smaller semantic differences
introduced through M2.

## Explicit non-goals

- sharding, `mongos`, balancer behavior, and shard keys;
- replica-set networking, elections, sync source selection, and rollback;
- multi-document ACID transactions, sessions, read/write concern, and MVCC;
- `$lookup`, change streams, TTL, text, wildcard, hashed, and geospatial
  indexes;
- MongoDB wire protocol, drivers, authentication, authorization, and server
  administration;
- binary BSON compatibility;
- WiredTiger compression, pages, cache eviction, concurrency, and checkpoints;
- JavaScript execution, schema validation, collation, regex, and full MQL.

## Milestone boundaries

- **M1 (implemented):** value/path semantics, CRUD, query/update subset,
  automatic `_id`, idempotent oplog, journal, checkpoint, recovery, labs.
- **M2 (implemented):** secondary/compound/unique/multikey indexes,
  prefix-aware selectivity, IXSCAN/COLLSCAN planning, `explain`, and the
  minimum aggregation pipeline.
- **M3 (not implemented):** capped/ring oplog retention and replication mapping
  to MiniDist. Only `oplog/capped.py` remains a documentation boundary.

## BSON and identity differences

- Documents are Python `dict` values and arrays are `list` values. Supported
  scalar values are `None`, bool, int/float, string, and MiniMongoDB `ObjectId`.
  Dates, binary, decimal, regex, timestamp, MinKey/MaxKey, code, and others are
  rejected.
- The local cross-type order is:
  `null < number < string < document < array < bool < objectId`.
  It is deliberately not the full BSON comparison order.
- Exact embedded-document equality treats field insertion order as
  significant. Persistence preserves that order using ordered key/value pairs.
- Real ObjectIds include non-deterministic/environment-derived material.
  MiniMongoDB's 24-hex-digit analogue is only an injected monotonic counter.
- The `_id` index recursively converts values to hashable canonical keys with
  BSON type tags. Thus `True` and `1` are distinct, while numerically equal
  int/float values share one identity, matching this project's `bson_equal`.

## Query differences

- Implemented operators are only `$eq` (including implicit equality),
  `$gt/$gte/$lt/$lte/$ne/$in/$exists/$and/$or/$not`.
- Field-level `$not` follows the supported MongoDB-shaped subset. MiniMongoDB
  additionally accepts `$not` as a top-level logical operator; real MongoDB
  does not support top-level `$not`. This is a project extension, not portable
  MQL behavior.
- Scalar equality and comparison inspect stored array elements recursively.
  Literal array equality remains whole-array and order-sensitive.
- Literal embedded documents use exact whole-value equality. Use a dotted path
  to select one nested field.
- Real MongoDB range predicates generally use type bracketing. MiniMongoDB
  instead compares supported unlike types using its documented global order.
- MongoDB `{field: null}` also matches missing fields. MiniMongoDB distinguishes
  null from missing; use `$exists: false` for missing.
- There is no `$elemMatch`; multiple predicates on an array path may therefore
  be satisfied by different elements.
- `find` has no projection, sort, skip, limit, cursor, collation, or regex
  options. It returns an eager list in insertion order, even when IXSCAN
  narrows the candidate set. Projection/sort/limit exist only as aggregation
  stages.

## Index and planner differences

- Secondary indexes are ascending-only ordered canonical maps, not B-trees.
  Dotted fields and compound leftmost prefixes are supported; descending,
  sparse, partial, wildcard, hashed, text, and geospatial indexes are absent.
- Index keys use the same recursive BSON-tagged canonical form as `_id`.
  Arrays expand recursively into per-element multikey entries and duplicate
  keys owned by the same document are de-duplicated.
- A compound index forms the Cartesian product when more than one indexed
  field contains arrays. Real MongoDB rejects a compound multikey index when
  more than one indexed field is an array in a document; this miniature keeps
  the product visible as a teaching simplification.
- Missing indexed fields use a null-like key. There is no sparse option, and a
  unique index therefore permits only one document with that missing/null key.
- Index creation validates current documents, appends a durable
  `create_index` entry, then publishes the definition. Definitions also enter
  checkpoints; document changes update every index only after journal success.
- The planner has no statistics catalog, histograms, plan cache, intersection,
  covered queries, sort satisfaction, or trial execution. It counts candidate
  owners for prefix-compatible indexes and chooses IXSCAN only when that count
  is smaller than the collection size.
- Safe `_id` equality uses the automatic `_id_` IXSCAN. Because this teaching
  model still permits a root array as `_id`, scalar predicates fall back to
  COLLSCAN when any such id exists so matcher element-expansion cannot be lost.
- `explain(query)` is an eager collection method rather than a cursor method.
  It reports one winning plan and `keysExamined/docsExamined/nReturned`; it has
  no verbosity modes, rejected plans, timing, yields, or storage metrics.

## Aggregation differences

- The implemented stages are only `$match/$project/$group/$sort/$limit`.
  `$match` reuses the normal matcher; there is no pipeline rewrite or index
  pushdown.
- `$group` supports `_id` plus `$sum/$avg/$min/$max/$push`. Expressions are
  constants, dotted `$field` references, or nested document/list shapes; the
  full MongoDB expression language is absent.
- `$match`, `$project`, and `$limit` stream. `$group` and `$sort` materialize
  input in memory. There is no spilling, parallelism, distributed merge,
  `$lookup`, `$unwind`, window functions, or optimizer.

## Update and CRUD differences

- Implemented update operators are only `$set/$unset/$inc/$push/$pull`.
  `$push` has no `$each/$slice/$sort/$position`; `$pull` accepts the local
  matcher subset.
- Paths may create missing dictionary parents. They never invent or extend a
  missing array; numeric indexes must already exist.
- `$unset` on an array index writes `None` to preserve positions, matching the
  useful MongoDB behavior, while unsetting a document key removes it.
- There are no upserts, array filters, positional `$` operators, bulk-write
  modes, find-and-modify variants, or write concern.
- `insert_many` validates the batch before making any document visible.
  Generated counter values consumed by a rejected batch are not rolled back.
- `insert_many`, `update_many`, and `delete_many` are not all-or-nothing
  durability transactions. `insert_many` validates all candidates first; each
  batch method then prepares and commits one document at a time. If journal
  append for item N fails, the earlier items remain durable and visible, item N
  and later items remain invisible, the failing sequence is not consumed, and
  the storage error is raised.
- Single-document mutation is atomic only in the single Python process: the
  engine builds and validates a copy before swapping it. There is no concurrent
  reader/writer isolation.

## Oplog differences

- MiniMongoDB emits one entry per affected document (plus index-definition
  entries), not a byte-compatible MongoDB oplog
  record.
- Insert/replace records carry a full document. Update records carry `$set` and
  `$unset` post-images for every requested path; `$inc`, `$push`, and `$pull`
  never survive into the entry.
- Delete replay is a no-op when the key is already absent. Insert/replace replay
  converges by `_id`.
- The in-memory oplog is unbounded. Capped retention is M3.
- There are no terms, timestamps, wall clocks, replica identities, majority
  commit points, rollback, or cross-node transport.

## Storage and crash differences

- The local journal frames logical oplog entries as
  `4-byte length | payload | 4-byte CRC32`. Real MongoDB uses WiredTiger's
  storage-engine journal separately from the replication oplog.
- Appends flush and `fsync` before the document, `_id`/secondary indexes,
  sequence, or in-memory oplog entry becomes visible. A failed append is best-effort
  truncated back to its prior boundary and the storage error is raised. There
  is no group commit.
- Only an invalid final frame is repaired by truncating to the last valid
  prefix. A CRC/decode failure before later bytes raises corruption instead of
  silently discarding history.
- Checkpoints serialize the whole database as tagged JSON, replace one file
  atomically, and `fsync` the parent directory after rename. They have no
  independent checksum, pages, compression, fuzzy checkpoint protocol, or
  concurrent-write coordination.
- Startup loads the checkpoint and replays only journal sequences newer than
  the snapshot. Replay does not recursively append new records.
- The public `inject_journal_tail_truncation` method exists only for
  deterministic teaching labs and tests; it is not a database administration
  feature.
