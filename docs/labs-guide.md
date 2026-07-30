# Chapter 4: Hands-on Experiments

[中文版](zh/labs-guide.md)

Run commands from the repository root after `uv sync`. The labs use public
APIs; the crash-recovery lab uses a temporary directory and leaves no database
files in the repository.

## Array and embedded-document matching

Source:
[lab_array_matching.py](https://github.com/system-in-miniature/MiniMongoDB/blob/main/labs/lab_array_matching.py)

```bash
uv run python labs/lab_array_matching.py
```

Expected: scalar array and dotted-path queries both print `['Ada']`; the
partial embedded-document literal prints `[]`. Watch the distinction between
array element traversal, exact whole-document equality, and explicit dotted
selection.

## Idempotent oplog replay

Source:
[lab_oplog_idempotent.py](https://github.com/system-in-miniature/MiniMongoDB/blob/main/labs/lab_oplog_idempotent.py)

```bash
uv run python labs/lab_oplog_idempotent.py
```

Expected: requested `{'$inc': {'count': 3}}` becomes stored
`{'$set': {'count': 5}}`; replaying once or twice produces the same document
with count `5`. Watch why the oplog records a convergent post-image rather than
the original non-idempotent action.

## Torn journal-tail recovery

Source:
[lab_crash_recovery.py](https://github.com/system-in-miniature/MiniMongoDB/blob/main/labs/lab_crash_recovery.py)

```bash
uv run python labs/lab_crash_recovery.py
```

Expected: before truncation, documents `1` and `2` are visible. After restart,
only checkpointed document `1` remains; the incomplete final journal frame is
discarded. The exact remaining-byte count is an implementation detail. Watch
the recovery boundary between an atomic checkpoint and the valid journal-frame
prefix.

Continue with the [MongoDB mapping](mapping.md) and
[declared differences](DIFFERENCES.md).
