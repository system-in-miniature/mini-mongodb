> **Language**: English | [简体中文](README.zh-CN.md)

# MiniMongoDB

[![CI](https://github.com/system-in-miniature/mini-mongodb/actions/workflows/ci.yml/badge.svg)](https://github.com/system-in-miniature/mini-mongodb/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) ![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue.svg)

MiniMongoDB is the seventh **System-in-Miniature** project: a deterministic,
single-process document database kernel written in Python. It is a teaching
model, not a MongoDB-compatible server—there is no wire protocol, JavaScript
shell, replica set, or claim of complete BSON/MQL compatibility.

The M1 data path is small enough to inspect end to end:

```text
Python dict/list document
→ dotted-path resolver
→ query matcher (including array element matching)
→ update or replacement routing
→ automatic unique _id index
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

## Implemented in M1

- nested dict/list values, deterministic counter-backed `ObjectId`, explicit
  type tags and a documented simplified cross-type order;
- dotted reads and updates, including numeric array indexes;
- insert/find/update/replace/delete one-or-many APIs;
- `$eq` (implicit or explicit), `$gt/$gte/$lt/$lte/$ne/$in/$exists`,
  `$and/$or/$not`;
- scalar predicates that automatically inspect stored array elements;
- `$set/$unset/$inc/$push/$pull` and immutable `_id`;
- automatic unique `_id` index and duplicate-key failure;
- per-document oplog entries that rewrite action updates to final `$set`
  post-images, plus idempotent replay;
- length+CRC journal frames, final-tail repair, atomic checkpoint snapshots,
  and checkpoint-plus-journal startup recovery.

M2 secondary/compound indexes, planning, `explain`, and aggregation are not
implemented. M3 capped oplog retention and replication mapping are not
implemented. Their package boundaries exist as planning docstrings so later
milestones extend the architecture instead of replacing toy modules.

## Directory guide

```text
src/minimongodb/
  bson/        values, ObjectId, exact equality, ordering, dotted paths
  query/       logical operators and array-aware matching
  update/      replacement routing and update operators
  index/       M1 unique _id index
  oplog/       post-image entries and idempotent replay; capped.py is M3
  storage/     tagged codec, CRC journal, checkpoint, recovery inputs
  plan/        M2 planning boundary only
  aggregate/   M2 pipeline boundary only
  collection.py
  database.py
labs/          three executable, public-API experiments
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
| How is a query expressed? | parsed SQL → plan tree | query document → recursive matcher |
| How is data changed? | row-oriented DML expressions | replacement or path update operators |
| What is identity? | declared PK/UNIQUE indexes | mandatory automatic `_id` index |
| What is the durable log? | physical/page-aware WAL | framed idempotent logical post-images |
| What is the key surprise? | NULL and three-valued logic | array auto-match vs exact document |

MiniPostgres is best followed top-down from SQL parsing through planning and the
Volcano executor. MiniMongoDB M1 is best followed inside-out: start at BSON
value/path semantics, then the matcher, then collection writes, and finally the
oplog/journal recovery chain. M2 will make the planning and aggregation
comparison more symmetrical.

See [concept mapping](docs/mapping.md) and
[declared differences](docs/DIFFERENCES.md) before treating a successful lab as
evidence about production MongoDB.

## Trademark Notice

MiniMongoDB is an independent educational project. It is not affiliated with, endorsed by, or sponsored by MongoDB, Inc.. "MongoDB" is a trademark of its respective owner.
