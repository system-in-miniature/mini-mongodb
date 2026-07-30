# Chapter 5: Durability and Recovery

[中文版](../zh/tutorial/05-durability.md)

An in-memory collection can declare success after changing Python objects. A
durable database needs a stronger boundary: after an acknowledged mutation,
restart must reconstruct it even if the process dies before a checkpoint.
MiniMongoDB implements that boundary with fsynced logical journal frames,
whole-database checkpoints, and prefix recovery.

## Learning objectives

By the end of this chapter, you will be able to:

- trace journal-first publication from `Database` to `Collection`;
- describe the length/payload/CRC frame and tail-repair rule;
- explain checkpoint temp-write, fsync, rename, and directory-fsync ordering;
- derive startup state from checkpoint sequence plus newer journal entries;
- distinguish batch committed-prefix behavior from a transaction; and
- state which durability claims do not transfer to real MongoDB.

## Wiring durability into the collection

`src/minimongodb/database.py::Database.__init__` owns one directory, one
`Journal`, one database-wide `Oplog`, and named `Collection` objects. The key
wiring is:

```python
self._journal = Journal(self.directory / "journal.bin")
self.oplog = Oplog(
    start_sequence=highest_sequence + 1,
    listener=self._journal.append,
)
```

Every collection created by the database receives that oplog. A collection
mutation calls `src/minimongodb/oplog/entry.py::Oplog.emit`. `emit` constructs
the next immutable `OplogEntry`, but before appending it to the in-memory
entries list or advancing the sequence, it calls the listener.

The listener is `src/minimongodb/storage/journal.py::Journal.append`. Only
after `append` returns does `Oplog.emit` publish the entry and consume the
sequence. Only after `emit` returns does `Collection.insert_many`, `_update`,
or `_delete` publish the document and index changes. That call ordering is the
journal-first invariant:

```text
candidate mutation
  -> encode journal entry
  -> append complete frame
  -> flush + fsync
  -> publish in-memory oplog/sequence
  -> publish documents and indexes
```

If open, write, or fsync fails, the storage exception propagates. The mutation
does not become visible, and its sequence is not consumed. `Journal.append`
records the previous file size and attempts `_rollback_append` on failure,
truncating and fsyncing back to the last boundary. That rollback is
best-effort; startup tail repair is the final defense if cleanup itself fails.

## Frame structure and corruption policy

`Journal.append` obtains deterministic bytes from
`src/minimongodb/storage/codec.py::encode_entry`. The codec converts every
supported value to a tagged JSON node, preserving type and document field
order. An entry becomes:

```text
4-byte big-endian payload length | payload | 4-byte CRC32(payload)
```

The length finds the frame boundary; the CRC detects incomplete or corrupted
content. `src/minimongodb/storage/journal.py::Journal.read_entries` scans bytes
from offset zero. It accepts only complete, CRC-valid, decodable frames.

Repair is deliberately conservative. An incomplete length, incomplete payload,
bad CRC, or undecodable payload in the final frame may be a torn crash tail.
With repair enabled, `_repair_or_raise` truncates the file to the last valid
frame boundary, flushes, fsyncs, and returns the valid entries.

The same error before later bytes is not treated as a harmless tail. A bad
nonfinal CRC or decode raises `JournalCorruptionError`. Silently dropping a
middle frame would keep later mutations without their causal predecessor and
could manufacture an invalid history. Prefix recovery means the database trusts
a contiguous valid prefix, not every individually decodable fragment.

CRC32 detects accidental corruption; it is not cryptographic authentication
and does not protect against malicious tampering. There is no group commit,
configurable sync policy, segment rotation, or background writer.

## Checkpoint publication

Replaying an ever-growing journal is correct but increasingly expensive.
`src/minimongodb/database.py::Database.checkpoint` gathers a whole-database
state containing the current oplog sequence, every collection's documents, and
secondary-index definitions. Index entries themselves are not serialized;
recovery rebuilds them from definitions and documents.

`src/minimongodb/storage/checkpoint.py::write_checkpoint` encodes that state
and writes `checkpoint.bin.tmp`. It flushes and fsyncs the temporary file, calls
`os.replace` to atomically publish it as `checkpoint.bin`, then opens and
fsyncs the parent directory.

Why fsync the directory? Renaming changes directory metadata. Fsyncing only the
file does not necessarily make the new directory entry durable across power
loss. The intended order is:

```text
write temporary snapshot
  -> flush + fsync temporary file
  -> atomic replace destination
  -> fsync parent directory
```

The checkpoint has no independent checksum. It is a whole tagged-JSON image,
not a fuzzy concurrent snapshot of pages. `Database` is explicitly
single-writer, and checkpointing has no concurrent-write coordination.

## Startup recovery

`src/minimongodb/storage/recovery.py::load_recovery_state` reads the checkpoint
or supplies an empty state, then reads and repairs the journal's valid prefix.
It does not mutate collections itself.

`Database.__init__` chooses the next oplog sequence above both the checkpoint
sequence and every valid journal entry. It also scans recovered identifiers so
the deterministic ObjectId counter does not reuse an existing value. Collection
names come from checkpoint documents, index definitions, and journal entries.

Recovery proceeds in three phases:

1. Rebuild checkpoint documents with
   `Collection._apply_oplog_entry` using synthetic insert entries.
2. Restore checkpoint index definitions and rebuild their entries from the
   documents.
3. Call `src/minimongodb/oplog/replay.py::replay` for journal entries whose
   sequence is greater than the checkpoint sequence.

`_apply_oplog_entry` is a recovery-only mutation path and emits no new log.
Insert and replacement converge by `_id`; update post-images apply final
`$set/$unset` assignments; deleting an already absent key is a no-op.
Reopening the same database therefore does not append entries during replay.

Filtering by `after_sequence` is what joins checkpoint and journal correctly.
The journal is not truncated after a checkpoint, so it may still contain
records represented in the snapshot. Reapplying only newer sequences avoids
duplicate work; idempotent post-images provide an additional safety property,
not a substitute for the sequence boundary.

## Batch partial failure

`Collection.insert_many` validates candidate documents and uniqueness before
publication, but after validation it emits and publishes one document at a
time. Update-many and delete-many likewise mutate per document. Suppose a
journal append fails for the third item:

- items one and two are already durable and visible;
- item three remains invisible and its sequence is reusable;
- later items have not been attempted;
- the storage error is raised to the caller.

This committed-prefix contract is explicit in
[update and CRUD differences](../DIFFERENCES.md#update-and-crud-differences).
It is stronger than uncontrolled partial mutation because the prefix matches
durable frames, but weaker than a multi-document transaction. A caller that
retries a batch must account for the already-committed prefix.

## Compared with real MongoDB

Real MongoDB separates the WiredTiger recovery journal from the replica-set
oplog. MiniMongoDB reuses logical oplog entries as local recovery records, a
semantically opposite architecture called out in the
[mapping table](../mapping.md#minimongodb--mongodb-mapping). Real systems have
pages, write-ahead logging details, group commit, compression, concurrent
checkpoints, recovery timestamps, write concern, replication commit points,
and far richer failure handling.

The transferable mechanisms are ordering and prefix reasoning: a mutation must
cross its durable acceptance boundary before volatile publication; a snapshot
must be atomically published; restart begins from a checkpoint and applies
newer valid log records. The local codec and file layout are teaching devices,
not MongoDB formats.

See [storage and crash differences](../DIFFERENCES.md#storage-and-crash-differences),
[oplog differences](../DIFFERENCES.md#oplog-differences), and the journal,
checkpoint, and recovery rows in the
[mapping](../mapping.md#minimongodb--mongodb-mapping).

## Hands-on experiment: tear the final frame

Run:

```bash
UV_CACHE_DIR=/tmp/minimongodb-uv-cache uv run python labs/lab_crash_recovery.py
```

Measured output:

```text
before injected crash: [{'_id': 1, 'state': 'checkpointed'}, {'_id': 2, 'state': 'torn-tail-write'}]
truncated journal tail; remaining bytes: 572
recovered documents: [{'_id': 1, 'state': 'checkpointed'}]
  The checkpoint survives; the incomplete final frame is discarded.
```

The first document appears in the checkpoint. The second was in a complete
frame before the lab deliberately removed three bytes; after restart, only the
valid prefix is accepted, and repair truncates the torn frame. The exact byte
count is deterministic for the current tagged codec.

This experiment uses local files and the direct API. It performs no socket,
replica-set, write-concern, or power-loss validation.

## Exercises

### 1. Understanding: why journal before indexes?

What failure would occur if the collection updated its document and indexes
before `Journal.append` fsynced?

??? note "Reference answer"

    A failed append could leave a mutation visible in memory with no durable
    record. The caller might observe it before restart, then lose it after
    restart. Publishing indexes early could also expose candidates inconsistent
    with recoverable documents. Journal-first ordering makes volatile state a
    consequence of durable acceptance.

### 2. Understanding: tail versus middle corruption

Why may recovery truncate an invalid final frame but must raise on a corrupt
frame followed by later bytes?

??? note "Reference answer"

    A crash can naturally interrupt the current append, so an invalid suffix
    after a valid prefix is repairable. Corruption in the middle breaks history;
    keeping later entries while dropping the damaged predecessor could violate
    causal state. The system cannot safely infer that the later bytes form an
    authoritative continuation.

### 3. Hands-on: verify restart does not relog

Create a temporary `Database`, insert one document, record
`journal.bin` size, reopen the database twice, and record the size after each
open. Acceptance: all three sizes are equal and every reopen returns the same
document. Do not edit `src/`.

??? note "Reference answer"

    Use `TemporaryDirectory`, `Path(directory, "journal.bin").stat().st_size`,
    and three `Database(directory)` constructions. `_apply_oplog_entry` emits
    no recursive oplog record, so opening is read/repair/replay rather than a
    new write. The printed sizes must be identical.

### 4. Hands-on: propose a checkpoint checksum

Draft, but do not apply, a diff design that detects checkpoint corruption.
Acceptance: define the framed format, checksum coverage, backward-compatibility
decision, error behavior, and tests for round trip, truncated file, flipped
payload byte, and atomic replacement.

??? note "Reference answer"

    One acceptable design mirrors the journal with a magic/version header,
    payload length, tagged payload, and CRC32 over the payload. `read_checkpoint`
    must validate every component before decoding and raise a dedicated
    corruption error; it must never silently treat an existing corrupt
    checkpoint as empty. Tests should retain the current temp-file fsync,
    `os.replace`, and parent-directory fsync assertions. The proposal must say
    whether old unframed checkpoints are rejected or migrated.

## Summary

Durability is an ordering contract. A database collection shares an oplog whose
listener appends and fsyncs a framed logical mutation before the sequence,
document, or indexes publish. Checkpoints use temp-write, file fsync, atomic
replace, and directory fsync. Startup trusts a CRC-valid journal prefix and
replays only sequences newer than the snapshot. With this foundation, Chapter
6 can focus on a related but distinct property: why the logical update stored
in that durable frame is safe to replay more than once.
