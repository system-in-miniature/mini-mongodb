# Chapter 6: The Oplog as a Convergence Log

Chapter 5 established the durability order: MiniMongoDB appends a framed record
to the journal before publishing a mutation in memory. This chapter studies the
logical record inside that frame. An oplog is often described as “a list of
writes,” but that phrase hides the most important design decision: should the
log remember the action a client requested, or the state a replica must reach?
MiniMongoDB chooses the second form.

## Learning objectives

By the end of this chapter, you will be able to:

- trace one update from `Collection._update` through `Oplog.emit` to
  `replay`;
- explain why `$inc` is rewritten as `$set` before it enters the oplog;
- predict the result of replaying insert, replace, update, and delete records
  more than once;
- identify the durability/publication boundary and the no-recursive-log
  recovery path; and
- distinguish MiniMongoDB's logical, in-process oplog from MongoDB's
  replication oplog and WiredTiger journal.

## 6.1 Commands describe intent; oplog entries describe convergence

Consider a counter whose current value is `2`. The client sends
`{"$inc": {"count": 3}}`. Repeating that command produces `8`, not `5`, so
the command is not idempotent. A recovering node may nevertheless encounter a
record whose effect it has already applied: a checkpoint may include the
effect, a transport may redeliver an entry, or a caller may deliberately replay
the same input twice. The durable representation should make repeated
application harmless.

The conversion happens in
`src/minimongodb/collection.py`, function `Collection._update`. It first calls
`apply_operator_update` on an isolated copy. Only after the complete candidate
document has been built and secondary indexes have validated it does `_update`
call `Collection._post_image_update`:

```python
self.oplog.emit(
    self.name,
    "update",
    original["_id"],
    self._post_image_update(candidate, update),
)
```

`Collection._post_image_update` does not copy the requested operators. It
enumerates every path named by those operators, reads the value from the final
candidate, and emits either `$set` with that value or `$unset` when the path is
missing. Thus the requested increment becomes
`{"$set": {"count": 5}}`. Repeating the assignment converges on `5`.

This is a *post-image by changed path*, not a full-document post-image. It is
smaller than replacing the entire document, but it still describes final
values. If a request unsets and then sets the same path, the function reads the
finished candidate once and records only the final `$set`. The source test
`test_post_image_keeps_only_the_final_state_for_a_repeated_path` in
`tests/test_oplog.py` fixes this contract.

The distinction is useful beyond databases. An action log says “perform this
transition”; a convergence log says “make this named state equal to that
value.” The latter is easier to retry, but it requires the primary to calculate
the result before recording it.

## 6.2 Entry shape and sequence ownership

In `src/minimongodb/oplog/entry.py`, `OplogEntry` is a frozen dataclass with
five fields: `sequence`, `collection`, `operation`, `key`, and optional
`payload`. The operation is one of the forms published by collection methods:

- `insert` and `replace` carry the complete resulting document;
- `update` carries `$set`/`$unset` final assignments;
- `delete` carries the identity key and no payload; and
- `create_index` carries the durable index definition.

`Oplog.emit` owns sequence allocation. It constructs an entry using the current
`_next_sequence`, clones the payload across the ownership boundary, and then
calls its optional listener. In a `Database`, that listener is the journal
append path. Only if the listener returns successfully does `emit` append the
entry to its in-memory list and increment the sequence.

```python
if self._listener is not None:
    self._listener(entry)
self._entries.append(entry)
self._next_sequence += 1
```

That ordering is not cosmetic. A failed durable append neither consumes the
sequence nor publishes the entry. Back in `Collection.insert_many`,
`Collection._update`, or `Collection._delete`, document and index mutation
also occurs after `emit`. Consequently a caller sees a committed prefix:
earlier per-document entries may be durable and visible, while the failing
document and every later one are absent. This is not a multi-document
transaction.

The oplog object itself is append-only and in memory. Its class docstring calls
it “v1” and states that capped retention is M3. The file
`src/minimongodb/oplog/capped.py` is only a boundary-setting docstring; it
exposes no pretend ring buffer. Therefore a long-running MiniMongoDB process
does not bound the in-memory list.

## 6.3 Replay is deliberately a different write path

`src/minimongodb/oplog/replay.py`, function `replay`, accepts an iterable of
entries and either one target `Collection` or a mapping of collection names to
collections. It skips entries whose sequence is at or below
`after_sequence`, routes each remaining record, calls
`Collection._apply_oplog_entry`, and returns the greatest sequence seen.
Database startup uses the sequence stored in the checkpoint so that only newer
journal records are applied.

The important part is what replay does *not* call. It does not invoke public
`insert_one`, `update_one`, or `delete_one`. Those methods would emit new
records while consuming old records, recursively growing the log. Instead,
`Collection._apply_oplog_entry` in `src/minimongodb/collection.py` mutates the
document and index structures directly and emits nothing.

Each operation has a convergent rule:

- Insert and replace share one branch. If the key is absent, append the
  payload; if present, replace the current document.
- Update is ignored when the key is absent. When present, applying its final
  `$set`/`$unset` assignments again yields the same state.
- Delete removes a present document and is a no-op when it is already absent.
- `create_index` delegates to `Collection._restore_index`, which returns early
  if the named definition is already installed.

Replay also maintains both the automatic `_id` index and every secondary
index. For insert/replace it calls `IdIndex.add` or
`Collection._replace_at`; for delete it removes index ownership before removing
the document. Idempotence would be hollow if the document converged while its
indexes drifted.

There is a deliberate precondition here: the stream is an ordered,
authoritative history. MiniMongoDB does not solve conflicting primaries,
causal reordering, terms, rollback, or majority commit. Idempotence makes
duplicate application safe; it does not make arbitrary reordering safe.

## 6.4 Compared with real MongoDB

Real MongoDB stores replication records in the capped `local.oplog.rs`
collection. Replica-set members tail that oplog, track timestamps and terms,
maintain majority commit information, and may roll back divergent history.
Update entry formats are versioned and substantially richer than this
teaching model. MongoDB also keeps the storage engine's recovery journal
separate from the replication oplog.

MiniMongoDB intentionally combines two roles: the logical `OplogEntry` is also
the payload framed by the local durability journal. It has an integer sequence,
no wall clock or term, no replica identity, no transport, no election, no
rollback, and no bounded retention. One entry is emitted per affected document,
so `update_many` can expose a durable prefix rather than one atomic oplog event.

The exact boundary is recorded in
[Differences: Oplog differences](../DIFFERENCES.md#oplog-differences) and
[Differences: Storage and crash differences](../DIFFERENCES.md#storage-and-crash-differences).
The mapping classifies `OplogEntry` as intentionally simplified, while
classifying use of logical oplog frames as a storage journal as semantically
opposite to MongoDB. See
[MiniMongoDB ↔ MongoDB mapping](../mapping.md#one-write-through-the-miniature)
for the complete write chain. Carry forward the convergence idea, not the file
format or operational guarantees.

## 6.5 Hands-on experiment: replay the same history twice

Run from the repository root. The explicit cache location makes the command
work in read-restricted development sandboxes as well as normal shells.

```bash
UV_CACHE_DIR=/tmp/minimongodb-uv-cache uv run python labs/lab_oplog_idempotent.py
```

Measured output:

```text
requested $inc: {'$inc': {'count': 3}}
stored oplog payload: {'$set': {'count': 5}}
  Repeating $inc would add twice; repeating $set converges on count=5.
after one replay: [{'_id': 'visits', 'count': 5}]
after two replays: [{'_id': 'visits', 'count': 5}]
same after replay twice: True
```

Read the first two lines as a boundary: the public update language contains an
action, but the replicated/durable language contains an assignment. The last
three lines demonstrate convergence, not merely equality of return codes.

Now run the focused executable contract:

```bash
UV_CACHE_DIR=/tmp/minimongodb-uv-cache uv run pytest -q tests/test_oplog.py
```

Measured output:

```text
.......                                                                  [100%]
7 passed in 0.05s
```

No socket or external MongoDB process is used; both commands were verified
against the repository's direct Python API.

## 6.6 Exercises

### Understanding 1: action versus state

Suppose the current document is `{"_id": 1, "n": 10}` and a client requests
`{"$inc": {"n": 2}}`. What must the update oplog payload contain, and why is
storing the original request unsafe?

??? note "Reference answer"
    It must contain `{"$set": {"n": 12}}`. Replaying `$inc` twice would reach
    `14`, while replaying `$set` twice still reaches `12`. The primary computes
    the post-image before it emits the entry.

### Understanding 2: publication failure

An oplog listener raises while accepting sequence 5. Which parts of sequence 5
may become visible, and what sequence will the next successful emit attempt?

??? note "Reference answer"
    None of entry 5, its document change, or its index changes become visible.
    `Oplog.emit` calls the listener before appending or incrementing, and
    collection mutation follows `emit`, so the next attempt also uses sequence
    5. Earlier committed entries remain visible.

### Hands-on 3: add a replay observer

On a throwaway branch, extend `replay` with an optional callback that receives
each entry actually applied (not skipped). Do not change the public collection
write path. Acceptance: add a test that replays sequences 1–3 with
`after_sequence=1` and asserts callbacks `[2, 3]`; then run
`uv run pytest -q tests/test_oplog.py`.

??? note "Reference answer"
    A minimal conceptual diff is:

    ```diff
    -def replay(entries, target, *, after_sequence=0):
    +def replay(entries, target, *, after_sequence=0, on_apply=None):
         ...
         collection._apply_oplog_entry(entry)
    +    if on_apply is not None:
    +        on_apply(entry)
    ```

    Put the callback after successful application so it never reports skipped
    or failed work. The acceptance test should collect
    `entry.sequence`. This tutorial does not apply the diff to `src/`.

## Summary

MiniMongoDB turns non-idempotent client intent into per-path post-image
assignments, durably accepts each entry before publication, and replays through
a log-free internal mutation path. Duplicate application converges, but the
model does not provide ordering repair, replica-set consensus, or
multi-document atomicity. Chapter 7 builds on the same publication boundary:
when a write changes one document, every canonical secondary-index key must
converge with it.
