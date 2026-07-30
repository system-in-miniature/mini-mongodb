> **Language**: English | [简体中文](zh/mapping.md)

# MiniMongoDB ↔ MongoDB mapping

The `Level` column is part of the teaching contract:

- **Equivalent** means the local mechanism preserves the named core invariant,
  not that its performance or implementation is production-equivalent.
- **Intentionally simplified** means the direction is the same but the surface
  or machinery is smaller.
- **Semantically opposite** means the miniature deliberately reverses an
  important real-system choice; never transfer that behavior by analogy.

| MiniMongoDB module | Real MongoDB concept/subsystem | Level | What to carry forward |
|---|---|---|---|
| `bson.types.ObjectId` | BSON ObjectId identity value | Semantically opposite | Both are 12-byte-shaped identities, but real ObjectIds encode time/process/random/counter material; this project bans those sources and uses one injected counter. |
| `bson.types` dict/list model | Binary BSON values and comparison order | Intentionally simplified | Values remain typed and documents/arrays remain distinct. The supported types and cross-type order are much smaller. |
| `bson.path` | MQL dotted field paths | Intentionally simplified | Nested fields and explicit numeric array indexes share one path notation; ambiguous sparse-array creation is rejected here. |
| `query.matcher` scalar-vs-array equality | MQL multikey matching behavior | Equivalent | A scalar predicate can match an element of a stored array without explicit iteration. |
| `query.matcher` literal document equality | BSON embedded-document equality | Equivalent | A literal embedded document is compared as a complete value, including field order; dotted paths select individual nested fields. |
| `query.matcher` range comparisons | MQL comparison predicates | Semantically opposite | MongoDB normally applies type bracketing to range predicates; MiniMongoDB exposes its global teaching order across supported types. |
| `query.matcher` top-level `$not` | field-level `$not` query operator | Semantically opposite | MiniMongoDB accepts a project-specific top-level logical `$not`; real MongoDB supports `$not` only as a field operator and rejects the top-level form. |
| `update.operators` | MQL update modifiers | Intentionally simplified | Replacement and operator update are separate; path changes are single-document atomic. Operator options and array filters are absent. |
| `index.IdIndex` | automatically-created unique `_id_` index | Equivalent | Every collection has identity uniqueness under BSON-typed equality before a write becomes visible. Canonical tagged keys back a Python hash map, not a B-tree. |
| `index.SecondaryIndex` | ascending secondary, compound, unique, and multikey indexes | Intentionally simplified | Dotted fields share `_id`'s canonical BSON-tagged equality; an array-bearing document owns multiple de-duplicated keys. Compound scans require a leftmost prefix. The local ordered map is not a B-tree and does not implement descending, sparse, partial, or specialized indexes. |
| `collection.Collection` | collection CRUD layer | Intentionally simplified | Documents cross a copy boundary and publish only after their journal entry is durable. Batch methods commit a prefix rather than acting as multi-document transactions. |
| `oplog.OplogEntry` | replica-set oplog post-image/idempotence discipline | Intentionally simplified | Action updates become repeat-safe final assignments. Real oplog formats and version-specific update encodings are richer. |
| `storage.journal` carrying oplog frames | WiredTiger journal plus replica oplog | Semantically opposite | Real MongoDB separates storage-engine recovery records from the replication oplog; M1 reuses logical oplog entries as its local durability journal. |
| `storage.checkpoint` | WiredTiger checkpoint | Intentionally simplified | Restart begins from a snapshot and applies newer durable records. The snapshot is whole-database tagged JSON, without pages or MVCC. |
| `storage.recovery` | startup recovery | Equivalent | Only a CRC-valid journal prefix is replayed, and replaying already-applied post-images is harmless. |
| `plan.choose_plan` | query planner and `explain` | Intentionally simplified | Prefix-compatible indexes estimate selectivity from candidate ownership. IXSCAN wins only when it examines fewer documents than COLLSCAN; explain reports the winning Mongo-named stage and actual key/document counts. |
| `aggregate.execute_pipeline` | aggregation pipeline execution | Intentionally simplified | `$match/$project/$group/$sort/$limit` compose as document operators; group supports `$sum/$avg/$min/$max/$push`. Streaming and blocking stage boundaries are explicit, without MongoDB's optimizer or distributed pipeline. |
| `oplog.capped` docstring | capped `local.oplog.rs` retention | Intentionally simplified | The interface direction is recorded, but bounded retention is an explicit M3 item. |

## One write through the miniature

```text
update_one({"_id": 1}, {"$inc": {"visits": 1}})
  → matcher selects one document
  → update engine mutates an isolated copy
  → immutable _id is validated
  → oplog prepares {"$set": {"visits": <final value>}}
  → journal appends length | payload | CRC and fsyncs
  → oplog publishes its sequence and in-memory entry
  → collection swaps the copy and all indexes atomically
```

The crucial ownership boundary is between the user command and the durable
entry. The command says *what action to attempt*; the entry says *which final
state to converge on*.

## Relation operators versus document pipelines

MiniPostgres turns parsed SQL over schema-bound rows into a plan tree whose
Volcano operators pull tuples from children. MiniMongoDB starts with an
already-shaped query document, chooses `IXSCAN` or `COLLSCAN`, then passes
self-shaped nested documents through aggregation stages. Both teach operator
composition and blocking boundaries (`Sort`/`Aggregate` versus `$sort/$group`);
only the relational side binds columns to a schema, while the document side
keeps dotted paths and multikey fan-out as runtime value semantics.
