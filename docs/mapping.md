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
| `update.operators` | MQL update modifiers | Intentionally simplified | Replacement and operator update are separate; path changes are single-document atomic. Operator options and array filters are absent. |
| `index.IdIndex` | automatically-created unique `_id_` index | Equivalent | Every collection has identity uniqueness before a write becomes visible. The data structure is a Python hash map, not a B-tree. |
| `collection.Collection` | collection CRUD layer | Intentionally simplified | Documents cross a copy boundary and writes report counts. There are no cursors, read concerns, sessions, or concurrent writers. |
| `oplog.OplogEntry` | replica-set oplog post-image/idempotence discipline | Intentionally simplified | Action updates become repeat-safe final assignments. Real oplog formats and version-specific update encodings are richer. |
| `storage.journal` carrying oplog frames | WiredTiger journal plus replica oplog | Semantically opposite | Real MongoDB separates storage-engine recovery records from the replication oplog; M1 reuses logical oplog entries as its local durability journal. |
| `storage.checkpoint` | WiredTiger checkpoint | Intentionally simplified | Restart begins from a snapshot and applies newer durable records. The snapshot is whole-database tagged JSON, without pages or MVCC. |
| `storage.recovery` | startup recovery | Equivalent | Only a CRC-valid journal prefix is replayed, and replaying already-applied post-images is harmless. |
| `plan` docstring | query planner and `explain` | Intentionally simplified | The boundary is reserved for M2; M1 does not claim a planner exists. |
| `aggregate` docstring | aggregation pipeline execution | Intentionally simplified | The boundary is reserved for M2; no fake pipeline is exposed in M1. |
| `oplog.capped` docstring | capped `local.oplog.rs` retention | Intentionally simplified | The interface direction is recorded, but bounded retention is an explicit M3 item. |

## One write through the miniature

```text
update_one({"_id": 1}, {"$inc": {"visits": 1}})
  → matcher selects one document
  → update engine mutates an isolated copy
  → immutable _id is validated
  → collection swaps the copy atomically
  → oplog records {"$set": {"visits": <final value>}}
  → journal appends length | payload | CRC and fsyncs
```

The crucial ownership boundary is between the user command and the durable
entry. The command says *what action to attempt*; the entry says *which final
state to converge on*.
