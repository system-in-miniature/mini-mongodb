# MiniMongoDB M1 Design and Implementation History

**Historical objective:** Build the deterministic M1 teaching kernel described by
`MiniMongoDB-design.md`, including document semantics, CRUD, idempotent oplog,
crash recovery, labs, and documentation.

**Architecture:** `Collection` owns documents, the `_id` index, and write
orchestration. Focused `bson`, `query`, `update`, `oplog`, and `storage`
packages own reusable mechanisms; `Database` combines collections with a
journal and checkpoint. M2/M3 packages exist only as documented boundaries.

**Tech Stack:** Python 3.12+, standard library runtime, pytest development,
uv/hatchling packaging.

---

### Milestone 1: Project scaffold and BSON value model

**Recorded file scope:**
- Added: `pyproject.toml`, `.gitignore`
- Added: `src/minimongodb/__init__.py`, `src/minimongodb/errors.py`
- Added: `src/minimongodb/bson/__init__.py`, `types.py`, `path.py`
- Evidence: `tests/test_bson.py`

- Historical test coverage included tests for deterministic `ObjectId`, type tags/order, deep cloning,
  exact nested-document equality, and dotted path reads/writes through arrays.
- Historical verification covered the named focused checks.
  because the public symbols do not exist.
- The recorded implementation included only the tested value/path API, including explicit missing-path
  sentinel behavior and list-index validation.
- Historical regression coverage included the BSON tests and keep them green.

### Milestone 2: Query matcher and array semantics

**Recorded file scope:**
- Added: `src/minimongodb/query/__init__.py`, `matcher.py`
- Evidence: `tests/test_query.py`
- Evidence: `tests/test_array_matching.py`

- Historical test coverage included focused tests for implicit/explicit equality, comparisons, `$ne`,
  `$in`, `$exists`, `$and`, `$or`, `$not`.
- Historical additions included a dedicated semantic group proving scalar predicates inspect array
  elements while a literal nested document requires whole-document equality
  and a dotted path traverses into that document.
- Historical verification covered the named focused checks.
  matcher.
- The recorded implementation included a matcher that separates path resolution, candidate expansion,
  literal equality, and operator evaluation.
- Historical regression coverage included both files and keep them green.

### Milestone 3: CRUD, update operators, and `_id` index

**Recorded file scope:**
- Added: `src/minimongodb/index/__init__.py`, `id_index.py`
- Added: `src/minimongodb/update/__init__.py`, `operators.py`
- Added: `src/minimongodb/collection.py`
- Evidence: `tests/test_crud.py`, `tests/test_update.py`

- Historical test coverage included tests for insert one/many, injected counter IDs, duplicate keys,
  find, delete, update one/many, replace, result counts, and copy isolation.
- Historical test coverage included operator tests for `$set/$unset/$inc/$push/$pull`, dotted paths,
  operator-vs-replacement routing, invalid mixed updates, and immutable `_id`.
- Historical verification covered the named focused checks.
- The recorded implementation included the unique `_id` map, result dataclasses, collection API, and
  update engine with atomic candidate-copy validation before replacement.
- Historical regression coverage included the focused tests and the earlier matcher tests.

### Milestone 4: Idempotent oplog

**Recorded file scope:**
- Added: `src/minimongodb/oplog/__init__.py`, `entry.py`, `replay.py`,
  `capped.py`
- Integrated: `src/minimongodb/collection.py`
- Evidence: `tests/test_oplog.py`

- Historical test coverage included tests showing every write emits an entry, update entries contain
  post-image `$set` values rather than non-idempotent `$inc`, delete is stable,
  and replaying the same entries twice yields identical state.
- Historical verification covered the named focused checks.
- The recorded implementation included deterministic sequence-numbered entries and an idempotent
  upsert/delete replayer; leave capped retention as an M3-only docstring.
- The recorded integration included oplog emission after successful collection mutation.
- Historical regression coverage included oplog and CRUD/update tests.

### Milestone 5: Journal, checkpoint, and startup recovery

**Recorded file scope:**
- Added: `src/minimongodb/storage/__init__.py`, `codec.py`, `journal.py`,
  `checkpoint.py`, `recovery.py`
- Added: `src/minimongodb/database.py`
- Evidence: `tests/test_storage.py`, `tests/test_recovery.py`

- Historical test coverage included tests for length+CRC journal frames, corrupt/truncated tail repair,
  checkpoint round-trip, restart from checkpoint plus journal, and crash
  injection by truncating a frame at every boundary.
- Historical verification covered the named focused checks.
- The recorded implementation included deterministic tagged JSON encoding, framed append/read/repair,
  atomic checkpoint replacement, and database startup recovery.
- The recorded invariant required recovered writes do not append duplicate journal records and
  replay is idempotent.
- Historical regression coverage included focused tests and the full suite.

### Milestone 6: Full architecture placeholders, labs, and documentation

**Recorded file scope:**
- Added: `src/minimongodb/plan/__init__.py`
- Added: `src/minimongodb/aggregate/__init__.py`
- Added: `labs/lab_array_matching.py`
- Added: `labs/lab_oplog_idempotent.py`
- Added: `labs/lab_crash_recovery.py`
- Added: `README.md`, `docs/mapping.md`, `docs/DIFFERENCES.md`
- Evidence: `tests/test_labs.py`

- Historical additions included tests that execute all three labs as scripts and assert their
  explanatory markers.
- Historical verification covered the named focused checks.
- The recorded implementation included labs using only exported `minimongodb` APIs.
- The recorded documentation covered quick start, tree, MiniPostgres comparison, mapping tiers,
  non-goals, BSON ordering differences, and every deliberate semantic gap.
- Historical additions included M2/M3 package docstrings without callable fake behavior.
- Historical verification covered the named focused checks.
  whitespace-error checks, deterministic-source scans, and line-count reporting.
