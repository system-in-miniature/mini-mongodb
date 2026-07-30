> **Language**: English | [简体中文](zh/DIFFERENCES.md)

# Differences from MongoDB

MiniMongoDB is a mechanism model, not a compatibility implementation. This
file records both the design's non-goals and smaller semantic differences
introduced by M1.

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
- **M2 (not implemented):** secondary/compound/unique indexes, selectivity,
  IXSCAN/COLLSCAN planning, `explain`, aggregation pipeline.
- **M3 (not implemented):** capped/ring oplog retention and replication mapping
  to MiniDist. `oplog/capped.py`, `plan/`, and `aggregate/` are documentation
  boundaries, not working substitutes.

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
- `_id` must be hashable because the M1 index is a Python map.

## Query differences

- Implemented operators are only `$eq` (including implicit equality),
  `$gt/$gte/$lt/$lte/$ne/$in/$exists/$and/$or/$not`.
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
- There is no projection, sort, skip, limit, cursor, collation, regex, or
  query-planner shortcut in M1. `find` returns an eager list in insertion order.

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
- Single-document mutation is atomic only in the single Python process: the
  engine builds and validates a copy before swapping it. There is no concurrent
  reader/writer isolation.

## Oplog differences

- M1 emits one entry per affected document, not a byte-compatible MongoDB oplog
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
- Appends flush and `fsync` before returning. There is no group commit.
- Only an invalid final frame is repaired by truncating to the last valid
  prefix. A CRC/decode failure before later bytes raises corruption instead of
  silently discarding history.
- Checkpoints serialize the whole database as tagged JSON and replace one file
  atomically. They have no independent checksum, pages, compression, fuzzy
  checkpoint protocol, or concurrent-write coordination.
- Startup loads the checkpoint and replays only journal sequences newer than
  the snapshot. Replay does not recursively append new records.
- The public `inject_journal_tail_truncation` method exists only for
  deterministic teaching labs and tests; it is not a database administration
  feature.
