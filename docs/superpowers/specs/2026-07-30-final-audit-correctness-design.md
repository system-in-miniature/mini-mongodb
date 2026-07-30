# Final Audit Correctness Design

## Scope

Fix the four MiniMongoDB findings from the 2026-07-30 final audit without
changing the public CRUD surface or adding transaction semantics.

## Write publication boundary

`Oplog.emit()` prepares an entry at the current sequence and invokes its
durability listener before changing the in-memory oplog or advancing the
sequence. A listener exception propagates unchanged and leaves both fields
unchanged. `Collection` prepares and validates each candidate, emits its
durable entry, and only then publishes the corresponding document/index
mutation.

Batch methods retain whole-batch input validation but are not atomic durability
transactions. They commit one matching document at a time. If journal append
for item N fails, items before N remain durable and visible, item N and later
items remain invisible, the failing sequence is reusable, and the original
storage exception is raised.

Journal append records the prior file length and best-effort truncates back to
that boundary after open/write/flush/fsync failure. This prevents a failed
operation from becoming replay-visible merely because failed-I/O test doubles
leave bytes in the page cache.

## BSON identity keys

The `_id` map uses a recursive canonical key prefixed by the same BSON-like
type tags used by `bson_equal`. Numeric int/float values share the `number`
tag and therefore collide exactly when Python numeric equality (the existing
BSON equality rule) says they are equal. Bool has a separate tag, NaN has a
stable token, and documents/arrays preserve recursive value and document-field
order semantics.

## Filesystem and semantic documentation

Checkpoint publication fsyncs the destination parent directory after
`os.replace`. Top-level `$not` remains implemented but both English and Chinese
differences/mapping pages label it as a project extension that real MongoDB
does not accept at top level, classified as `Semantically opposite`.

## Verification

Tests inject journal open, write, and fsync failures and assert live visibility,
oplog sequence, retry behavior, and restart state. Additional tests cover
`True` versus `1`, equal int/float IDs, non-equal large int/float IDs, and
checkpoint parent-directory fsync. The final gate was the complete test suite.
