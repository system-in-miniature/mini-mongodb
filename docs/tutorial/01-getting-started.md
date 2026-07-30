# Chapter 1: Meet MiniMongoDB

[中文版](../zh/tutorial/01-getting-started.md)

MiniMongoDB is a small, deterministic document-database kernel written in
Python. It is deliberately large enough to expose the mechanisms that make a
document database interesting—typed values, array-aware queries, update
operators, indexes, a planner, an oplog, a journal, checkpoints, recovery, and
aggregation—but small enough that one reader can follow a write from the API
to durable bytes. It is not a MongoDB server and does not implement the MongoDB
wire protocol.

## Learning objectives

By the end of this chapter, you will be able to:

- create an in-memory `Collection`, insert a document, and query it;
- explain why MiniMongoDB copies documents at both API boundaries;
- trace the public `insert_one` and `find` calls to their source functions;
- distinguish an educational mechanism model from a compatibility server; and
- locate each major subsystem that later chapters will examine.

## Why learn from a miniature?

Production MongoDB includes networking, authentication, replication, sharding,
transactions, a query optimizer, a storage engine, operational tooling, and
years of compatibility behavior. Those are essential in production, but they
make a first source-reading pass difficult: a single insert crosses many
boundaries before the underlying idea becomes visible.

MiniMongoDB removes deployment scale, not the causal chain. A document still
crosses an ownership boundary. An identity is still checked before
publication. A durable database still records a mutation before making it
visible. Recovery still combines a checkpoint with later log records. The
miniature is useful because those decisions appear as short Python functions
rather than as a large distributed call graph.

This distinction controls how to read the whole book. Do not ask, “Could I
point an official MongoDB driver at this package?” The answer is no. Ask,
“Which invariant is this small function making explicit, and where does a
production database need a more sophisticated implementation?” The
[mapping table](../mapping.md) labels each correspondence as equivalent,
intentionally simplified, or semantically opposite. The
[differences reference](../DIFFERENCES.md) records omissions and nonportable
semantics.

## The first API boundary

The public surface is collected in `src/minimongodb/__init__.py`. Applications
normally begin with `Collection` for an ephemeral model or `Database` for a
directory-backed durable model. Result objects such as `InsertOneResult` and
`UpdateResult` resemble driver results without pretending to be PyMongo
classes.

The first important path is
`src/minimongodb/collection.py::Collection.insert_one`. It delegates to
`Collection.insert_many` even for one document:

```python
def insert_one(self, document):
    return InsertOneResult(self.insert_many([document]).inserted_ids[0])
```

That delegation gives single and batch inserts the same validation,
identifier, logging, and publication rules. In `Collection.insert_many`, each
input passes through `src/minimongodb/bson/types.py::clone_document`. The
function validates the complete supported BSON-shaped tree and then performs a
deep copy. If `_id` is absent, the collection invokes its injected
`CounterObjectIdGenerator`. It then computes a typed canonical key and checks
the unique `_id` index.

The copy is not cosmetic. Without it, this sequence would corrupt storage:

```python
source = {"profile": {"city": "London"}}
collection.insert_one(source)
source["profile"]["city"] = "changed elsewhere"
```

MiniMongoDB owns a copy, so later caller mutation cannot alter stored state.
The read path repeats the boundary. `Collection.find` calls
`Collection._run_query`, then clones every matched document before returning
it. A caller can mutate a result without mutating the database. These two
copies are an intentionally visible substitute for the serialization and
buffer ownership boundaries that naturally separate a client from a real
server.

## Insert, publish, then find

After validation, `Collection.insert_many` processes candidates in input
order. For each candidate it calls
`src/minimongodb/oplog/entry.py::Oplog.emit`, then appends the document to
`_documents`, adds it to `IdIndex`, and updates secondary indexes. An
in-memory collection has no journal listener, so `emit` records directly in
its local oplog. A directory-backed `Database` supplies
`src/minimongodb/storage/journal.py::Journal.append` as the listener; Chapter 5
will show why that changes the publication boundary.

Queries enter `src/minimongodb/collection.py::Collection._run_query`. Before
planning, it calls `src/minimongodb/query/matcher.py::matches` against an empty
document. `matches` first runs the independent `validate_query` pass over the
complete operator structure, before attempting any document-dependent match;
therefore malformed queries are rejected even when the collection has no
data. `_run_query` then asks
`src/minimongodb/plan/__init__.py::choose_plan` for either a collection scan or
an index scan. Regardless of the candidate source, the same `matches`
function decides semantics. Planning may reduce work; it must never change
which documents match. Results remain in insertion order to keep labs and
tests deterministic.

That is already a complete database-shaped loop:

```text
caller document
  -> validate and clone
  -> assign/check _id
  -> emit mutation
  -> publish document and indexes
  -> plan query
  -> match candidates
  -> clone returned documents
```

Determinism is a teaching feature throughout the project.
`CounterObjectIdGenerator` produces predictable identifiers, collection
storage preserves insertion order, oplog sequences start from a known value,
and labs avoid wall-clock races. Determinism does not mean production MongoDB
behaves this way; it means the same experiment reveals the same mechanism on
every run.

## The map of the book

The next four chapters cover the write/read foundation. Chapter 2 examines the
document model: explicit type tags, equality, comparison, and dotted paths.
Chapter 3 follows query evaluation, especially the subtle difference among a
scalar predicate on an array, a whole-array literal, an embedded-document
literal, and a dotted path. Chapter 4 studies operator updates and replacement
updates, including immutable `_id`. Chapter 5 moves from an in-memory
collection to journal-first durability, checkpoints, and crash recovery.

The second half builds on those invariants. Chapter 6 explains why action
updates such as `$inc` become idempotent post-images in the oplog. Chapters 7
and 8 cover secondary indexes, multikey expansion, planning, and `explain`.
Chapter 9 treats aggregation as a chain of streaming and blocking document
operators. Chapter 10 compares document and relational models and closes with
the limits of miniature-based reasoning.

The directory layout mirrors that progression:

- `bson/` owns value identity, comparison, copying, and paths;
- `query/` decides whether a document matches a query;
- `update/` computes a new document without mutating the stored original;
- `collection.py` coordinates CRUD, logging, indexes, and query execution;
- `oplog/` represents repeat-safe logical changes;
- `storage/` owns encoding, journal frames, checkpoints, and recovery;
- `index/` and `plan/` narrow candidate documents without redefining matches;
- `aggregate/` composes document-to-document pipeline stages.

When a behavior surprises you, locate its owner before changing it. Array
matching belongs in the matcher, not in the planner. Durable acceptance belongs
before collection publication, not after an index update. This ownership map is
more valuable than memorizing individual methods.

## Compared with real MongoDB

The closest real-MongoDB operation is an `insertOne()` followed by `find()`.
Real clients send BSON commands over the MongoDB wire protocol to `mongod`;
server command handling, authorization, concurrency control, replication, and
WiredTiger then participate. MiniMongoDB is an in-process Python API with no
socket, driver session, read concern, write concern, or concurrent
reader/writer isolation.

Its documents are Python dictionaries and lists, not binary BSON. Its
ObjectId-shaped value is a deterministic counter, not a production ObjectId.
Its in-memory list is not WiredTiger. Its result classes are teaching
interfaces, not a driver-compatibility promise. See
[BSON and identity differences](../DIFFERENCES.md#bson-and-identity-differences),
[update and CRUD differences](../DIFFERENCES.md#update-and-crud-differences),
and the `collection.Collection` row in the
[mapping](../mapping.md#minimongodb--mongodb-mapping).

Those differences are not fine print. They identify the exact boundary of
each inference: this repository can teach ownership, validation order,
identity, and matching; it cannot prove wire compatibility, distributed
durability, or production performance.

## Hands-on experiment: the first conversation

Run from the repository root. In a normal writable environment,
`UV_CACHE_DIR=...` may be omitted. It is shown because it also works when the
default uv cache is read-only.

```bash
UV_CACHE_DIR=/tmp/minimongodb-uv-cache uv run python - <<'PY'
from minimongodb import Collection, CounterObjectIdGenerator
people = Collection("people", id_generator=CounterObjectIdGenerator(7))
result = people.insert_one({"name": "Ada", "skills": ["Python", "databases"]})
print("inserted:", result.inserted_id)
print("found:", people.find({"skills": "Python"}))
PY
```

Measured output:

```text
inserted: 000000000000000000000007
found: [{'name': 'Ada', 'skills': ['Python', 'databases'], '_id': ObjectId('000000000000000000000007')}]
```

The injected generator explains the stable identifier. The query operand is a
scalar while the stored value is an array; the matcher inspects array elements,
so `"Python"` matches. Chapter 3 will derive that rule from the source.

This is a direct-API experiment. It performs no network or socket validation
and therefore is not evidence of MongoDB driver compatibility.

## Exercises

### 1. Understanding: why copy twice?

Explain why MiniMongoDB clones on insert and again on find. Your answer should
name the two different owners protected by those copies.

??? note "Reference answer"

    The insert copy prevents caller-owned mutable objects from becoming
    database storage. The find copy prevents database-owned nested objects
    from escaping to the caller. Together they establish an ownership boundary
    in both directions.

### 2. Hands-on: prove read isolation

Write an inline `uv run python` experiment that inserts a nested document,
mutates the object returned by `find_one`, and prints a second `find_one`.
Acceptance: the second result must retain the original nested value. Do not
change `src/`.

??? note "Reference answer"

    ```bash
    uv run python - <<'PY'
    from minimongodb import Collection
    c = Collection()
    c.insert_one({"_id": 1, "nested": {"value": "stored"}})
    result = c.find_one({"_id": 1})
    result["nested"]["value"] = "caller"
    print(c.find_one({"_id": 1}))
    PY
    ```

    Acceptance output is
    `{'_id': 1, 'nested': {'value': 'stored'}}`.

### 3. Hands-on: inspect deterministic insertion order

Insert three explicitly identified documents, query all documents, and print
their identifiers. Acceptance: output is `[3, 1, 2]` when that is the insertion
order, demonstrating the public deterministic-order contract rather than a
sorted query.

??? note "Reference answer"

    Use `Collection.insert_many([{"_id": 3}, {"_id": 1}, {"_id": 2}])`, then
    print `[doc["_id"] for doc in collection.find()]`. The expected output is
    `[3, 1, 2]`. Production MongoDB does not promise this as a general natural
    ordering contract.

## Summary

MiniMongoDB is useful because it preserves database mechanisms while replacing
production scale with deterministic, inspectable Python. A call to
`Collection.insert_one` validates and copies a document, establishes identity,
emits a mutation, and publishes state; `find` plans, matches, and returns a new
copy. The next chapter opens the value layer beneath both operations: what
counts as a supported BSON-shaped value, how equality differs from Python
equality, and how a dotted path traverses a document.
