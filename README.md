> **Language**: English | [简体中文](README.zh-CN.md)

# MiniMongoDB

[![CI](https://github.com/system-in-miniature/mini-mongodb/actions/workflows/ci.yml/badge.svg)](https://github.com/system-in-miniature/mini-mongodb/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) ![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue.svg)

MiniMongoDB is the seventh **System-in-Miniature** project: a deterministic,
single-process document database kernel written in Python. It is a teaching
model, not a MongoDB-compatible server—there is no wire protocol, JavaScript
shell, replica set, or claim of complete BSON/MQL compatibility.

The M2 data path is small enough to inspect end to end:

```text
Python dict/list document
→ dotted-path resolver
→ query matcher (including array element matching)
→ update or replacement routing
→ automatic _id plus secondary/compound multikey indexes
→ COLLSCAN/IXSCAN planner and explain counters
→ idempotent post-image oplog
→ CRC journal + checkpoint
→ startup recovery
```

The central lesson is a MongoDB behavior that often surprises SQL users:

```python
from minimongodb import Collection

people = Collection("people")
people.insert_one(
    {
        "name": "Ada",
        "tags": ["database", "python"],
        "profile": {"city": "London", "role": "engineer"},
    }
)

assert people.find({"tags": "python"})       # scalar checks array elements
assert not people.find({"profile": {"city": "London"}})  # exact document
assert people.find({"profile.city": "London"})            # dotted field
```

## Quick start

Python 3.12 or newer and [uv](https://docs.astral.sh/uv/) are required.
Runtime code has zero third-party dependencies; the development group contains
only pytest.

```bash
uv sync
uv run pytest -q
uv run python labs/lab_array_matching.py
uv run python labs/lab_oplog_idempotent.py
uv run python labs/lab_crash_recovery.py
uv run python labs/lab_multikey_index.py
uv run python labs/lab_explain.py
```

Persistent use starts with an explicit directory:

```python
from minimongodb import Database

database = Database("./demo-data")
users = database.get_collection("users")
users.insert_one({"name": "Ada", "visits": 1})
users.update_one({"name": "Ada"}, {"$inc": {"visits": 1}})
database.checkpoint()

restarted = Database("./demo-data")
print(restarted["users"].find())
```

All returned documents are copies. The database owns its stored values, so a
caller cannot mutate persistence by changing a result dictionary.

## Implemented through M2

- nested dict/list values, deterministic counter-backed `ObjectId`, explicit
  type tags and a documented simplified cross-type order;
- dotted reads and updates, including numeric array indexes;
- insert/find/update/replace/delete one-or-many APIs;
- `$eq` (implicit or explicit), `$gt/$gte/$lt/$lte/$ne/$in/$exists`,
  `$and/$or/$not`;
- scalar predicates that automatically inspect stored array elements;
- `$set/$unset/$inc/$push/$pull` and immutable `_id`;
- automatic unique `_id` index and duplicate-key failure;
- single-field and compound ascending indexes over dotted paths, canonical
  BSON-tagged keys, multikey array expansion, and optional uniqueness;
- deterministic prefix-aware COLLSCAN/IXSCAN selection and `explain` execution
  counts;
- `$match/$project/$group/$sort/$limit` pipelines, including
  `$sum/$avg/$min/$max/$push` group accumulators;
- per-document oplog entries that rewrite action updates to final `$set`
  post-images, plus idempotent replay;
- length+CRC journal frames, final-tail repair, atomic checkpoint snapshots,
  and checkpoint-plus-journal startup recovery.

M3 capped oplog retention and replication mapping are not implemented. Index
definitions are journaled and checkpointed; document writes still publish the
document, `_id` index, and all secondary entries only after the journal append
succeeds.

## Directory guide

```text
src/minimongodb/
  bson/        values, ObjectId, exact equality, ordering, dotted paths
  query/       logical operators and array-aware matching
  update/      replacement routing and update operators
  index/       unique _id plus canonical compound/multikey indexes
  oplog/       post-image entries and idempotent replay; capped.py is M3
  storage/     tagged codec, CRC journal, checkpoint, recovery inputs
  plan/        selectivity estimate, COLLSCAN/IXSCAN choice, explain plan
  aggregate/   match/project/group/sort/limit operator pipeline
  collection.py
  database.py
labs/          five executable, public-API experiments
tests/         mechanism-focused tests, including crash boundaries
docs/          real-system mapping and declared differences
```

## Read beside MiniPostgres: relation versus document

Read the two projects by following the same questions through different data
models:

| Question | MiniPostgres | MiniMongoDB |
|---|---|---|
| What is stored? | schema-typed rows in relations | self-shaped nested documents |
| How is a field selected? | bound column reference | dotted path with array traversal |
| How is a query expressed? | parsed SQL → plan tree | query document → matcher + IXSCAN/COLLSCAN plan |
| How is data changed? | row-oriented DML expressions | replacement or path update operators |
| What is identity? | declared PK/UNIQUE indexes | mandatory automatic `_id` index |
| What is the durable log? | physical/page-aware WAL | framed idempotent logical post-images |
| What is the key surprise? | NULL and three-valued logic | array auto-match vs exact document |

MiniPostgres is best followed top-down from SQL parsing through planning and the
Volcano executor. MiniMongoDB is best followed inside-out: BSON value/path
semantics feed the matcher and canonical multikey indexes, then the planner
chooses a Mongo-named scan, and aggregation composes document operators as a
pipeline. Both projects expose planning and operator flow, but one transforms
schema-bound rows while the other preserves self-shaped nested documents.

See [concept mapping](docs/mapping.md) and
[declared differences](docs/DIFFERENCES.md) before treating a successful lab as
evidence about production MongoDB.

## Trademark Notice

MiniMongoDB is an independent educational project. It is not affiliated with, endorsed by, or sponsored by MongoDB, Inc.. "MongoDB" is a trademark of its respective owner.

## Verification

On 2026-08-10, the acceptance candidate completed the full test suite. The
independent [planner-work evidence package](bench/PROTOCOL.md) also compares the
same 1%-selective query before and after indexing at 100, 1,000, and 10,000
documents. At 10,000 documents, IXSCAN reduced `docsExamined` from 10,000 to
100 (100x less deterministic planner work) while preserving identical results.
This is an explain-counter result, not a wall-time or production MongoDB claim.
