# MiniMongoDB: A Document Database in Miniature

[中文版](zh/index.md)

MiniMongoDB is a deterministic, single-process Python kernel for learning how
a document database owns values, matches arrays, applies atomic
single-document updates, makes writes durable, replays an oplog, maintains
multikey indexes, chooses query plans, and executes aggregation pipelines.

This book follows mechanisms in dependency order. Each chapter anchors its
claims to concrete functions under `src/minimongodb/`, contrasts the miniature
with real MongoDB, includes a measured experiment, and ends with exercises
whose proposed source changes are not applied to `src/`.

## Before you begin

You need Python 3.12+ and [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/system-in-miniature/mini-mongodb.git
cd mini-mongodb
uv sync
uv run pytest -q
```

MiniMongoDB is an in-process teaching kernel, not a MongoDB-compatible server.
It has no MongoDB wire protocol or driver endpoint. Keep the
[mechanism mapping](mapping.md) and [differences](DIFFERENCES.md) open while
reading so that equivalent, simplified, and opposite behaviors stay separate.

## Book contents

1. [Meet MiniMongoDB](tutorial/01-getting-started.md) — positioning,
   environment, the first `insert`/`find`, and the complete system map.
2. [The Document Model](tutorial/02-document-model.md) — BSON-shaped type
   tags, comparison order, typed identity, and dotted paths.
3. [Query Semantics](tutorial/03-queries.md) — operators and the crucial
   distinction among array fan-out, exact whole values, and dotted paths.
4. [Update Operators](tutorial/04-updates.md) — `$set/$inc/$push/$pull`,
   replacement updates, immutable `_id`, and copy-first atomicity.
5. [Durability and Recovery](tutorial/05-durability.md) — journal-first
   publication, committed prefixes, checkpoints, and startup recovery.
6. [The Oplog](tutorial/06-oplog.md) — post-image rewriting and why replaying
   `$inc` as `$set` makes recovery idempotent.
7. [Secondary Indexes](tutorial/07-secondary-indexes.md) — compound, unique,
   and multikey indexes built from canonical typed keys.
8. [Planning and Explain](tutorial/08-planner-explain.md) — IXSCAN versus
   COLLSCAN, leftmost prefixes, selectivity, and scan counters.
9. [Aggregation Pipelines](tutorial/09-aggregation.md) —
   `$match/$project/$group/$sort/$limit` as streaming and blocking stages.
10. [Relational versus Document](tutorial/10-relational-vs-document.md) — a
    systematic comparison with MiniPostgres and the limits of each model.

## Reference material

Use the [repository README](https://github.com/system-in-miniature/mini-mongodb#readme)
for the implemented feature inventory and source directory guide. The
[mechanism mapping](mapping.md) is the parity ledger; the
[differences chapter](DIFFERENCES.md) is the semantic boundary; and the
[lab guide](labs-guide.md) collects runnable demonstrations. Construction-time
plans are retained in the [design history archive](superpowers/README.md), but
the tutorial, current source, and tests define behavior.
