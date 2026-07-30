# MiniMongoDB M1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> to implement this plan task-by-task. This repository is the user-selected
> empty target, execution is inline, and the user explicitly forbids commits.

**Goal:** Build the deterministic M1 teaching kernel described by
`MiniMongoDB-design.md`, including document semantics, CRUD, idempotent oplog,
crash recovery, labs, and documentation.

**Architecture:** `Collection` owns documents, the `_id` index, and write
orchestration. Focused `bson`, `query`, `update`, `oplog`, and `storage`
packages own reusable mechanisms; `Database` combines collections with a
journal and checkpoint. M2/M3 packages exist only as documented boundaries.

**Tech Stack:** Python 3.12+, standard library runtime, pytest development,
uv/hatchling packaging.

---

### Task 1: Project scaffold and BSON value model

**Files:**
- Create: `pyproject.toml`, `.gitignore`
- Create: `src/minimongodb/__init__.py`, `src/minimongodb/errors.py`
- Create: `src/minimongodb/bson/__init__.py`, `types.py`, `path.py`
- Test: `tests/test_bson.py`

- [ ] Write tests for deterministic `ObjectId`, type tags/order, deep cloning,
  exact nested-document equality, and dotted path reads/writes through arrays.
- [ ] Run `uv run pytest -q tests/test_bson.py`; verify collection fails
  because the public symbols do not exist.
- [ ] Implement only the tested value/path API, including explicit missing-path
  sentinel behavior and list-index validation.
- [ ] Re-run the BSON tests and keep them green.

### Task 2: Query matcher and array semantics

**Files:**
- Create: `src/minimongodb/query/__init__.py`, `matcher.py`
- Test: `tests/test_query.py`
- Test: `tests/test_array_matching.py`

- [ ] Write focused tests for implicit/explicit equality, comparisons, `$ne`,
  `$in`, `$exists`, `$and`, `$or`, `$not`.
- [ ] Add a dedicated semantic group proving scalar predicates inspect array
  elements while a literal nested document requires whole-document equality
  and a dotted path traverses into that document.
- [ ] Run the two test files and verify failures are caused by the absent
  matcher.
- [ ] Implement a matcher that separates path resolution, candidate expansion,
  literal equality, and operator evaluation.
- [ ] Re-run both files and keep them green.

### Task 3: CRUD, update operators, and `_id` index

**Files:**
- Create: `src/minimongodb/index/__init__.py`, `id_index.py`
- Create: `src/minimongodb/update/__init__.py`, `operators.py`
- Create: `src/minimongodb/collection.py`
- Test: `tests/test_crud.py`, `tests/test_update.py`

- [ ] Write tests for insert one/many, injected counter IDs, duplicate keys,
  find, delete, update one/many, replace, result counts, and copy isolation.
- [ ] Write operator tests for `$set/$unset/$inc/$push/$pull`, dotted paths,
  operator-vs-replacement routing, invalid mixed updates, and immutable `_id`.
- [ ] Run the CRUD/update tests and verify the expected missing API failures.
- [ ] Implement the unique `_id` map, result dataclasses, collection API, and
  update engine with atomic candidate-copy validation before replacement.
- [ ] Re-run the focused tests and the earlier matcher tests.

### Task 4: Idempotent oplog

**Files:**
- Create: `src/minimongodb/oplog/__init__.py`, `entry.py`, `replay.py`,
  `capped.py`
- Integrate: `src/minimongodb/collection.py`
- Test: `tests/test_oplog.py`

- [ ] Write tests showing every write emits an entry, update entries contain
  post-image `$set` values rather than non-idempotent `$inc`, delete is stable,
  and replaying the same entries twice yields identical state.
- [ ] Run the oplog tests and verify they fail for the missing implementation.
- [ ] Implement deterministic sequence-numbered entries and an idempotent
  upsert/delete replayer; leave capped retention as an M3-only docstring.
- [ ] Integrate oplog emission after successful collection mutation.
- [ ] Re-run oplog and CRUD/update tests.

### Task 5: Journal, checkpoint, and startup recovery

**Files:**
- Create: `src/minimongodb/storage/__init__.py`, `codec.py`, `journal.py`,
  `checkpoint.py`, `recovery.py`
- Create: `src/minimongodb/database.py`
- Test: `tests/test_storage.py`, `tests/test_recovery.py`

- [ ] Write tests for length+CRC journal frames, corrupt/truncated tail repair,
  checkpoint round-trip, restart from checkpoint plus journal, and crash
  injection by truncating a frame at every boundary.
- [ ] Run storage/recovery tests and verify expected missing API failures.
- [ ] Implement deterministic tagged JSON encoding, framed append/read/repair,
  atomic checkpoint replacement, and database startup recovery.
- [ ] Ensure recovered writes do not append duplicate journal records and
  replay is idempotent.
- [ ] Re-run focused tests and the full suite.

### Task 6: Full architecture placeholders, labs, and documentation

**Files:**
- Create: `src/minimongodb/plan/__init__.py`
- Create: `src/minimongodb/aggregate/__init__.py`
- Create: `labs/lab_array_matching.py`
- Create: `labs/lab_oplog_idempotent.py`
- Create: `labs/lab_crash_recovery.py`
- Create: `README.md`, `docs/mapping.md`, `docs/DIFFERENCES.md`
- Test: `tests/test_labs.py`

- [ ] Add tests that execute all three labs as scripts and assert their
  explanatory markers.
- [ ] Run lab tests and verify failure before scripts exist.
- [ ] Implement labs using only exported `minimongodb` APIs.
- [ ] Document quick start, tree, MiniPostgres comparison, mapping tiers,
  non-goals, BSON ordering differences, and every deliberate semantic gap.
- [ ] Add M2/M3 package docstrings without callable fake behavior.
- [ ] Run `uv run pytest -q`, all labs directly, `python -m compileall`,
  `git diff --check`, deterministic-source scans, and line-count reporting.
