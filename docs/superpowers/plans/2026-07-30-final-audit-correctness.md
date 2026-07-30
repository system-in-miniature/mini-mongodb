# Final Audit Correctness Design and Implementation History

**Historical objective:** Make durable journal success the publication boundary, align `_id`
identity with BSON equality, harden checkpoint rename durability, and document
the top-level `$not` extension.

**Architecture:** `Oplog` owns sequence/oplog publication ordering while
`Collection` owns document/index publication. `Journal` rolls failed appends
back to their previous byte boundary. BSON canonical keys are shared by batch
validation and `IdIndex`.

**Tech Stack:** Python 3.12+, standard library, pytest, uv.

---

### Milestone 1: Journal-first failure contract

**Recorded file scope:**
- Changed: `tests/test_recovery.py`
- Changed: `tests/test_oplog.py`
- Changed: `src/minimongodb/oplog/entry.py`
- Changed: `src/minimongodb/storage/journal.py`
- Changed: `src/minimongodb/collection.py`

- Historical additions included parametrized open/write/fsync failure tests covering visibility,
  sequence, retry, and restart.
- The initial failure evidence showed that sequences could publish before journal success.
- The recorded workflow made listener success precede oplog publication and made each collection
  mutation emit before document/index publication.
- Roll a failed journal append back to its original byte boundary.
- Historical regression coverage included focused tests.

### Milestone 2: BSON canonical `_id` keys

**Recorded file scope:**
- Changed: `tests/test_crud.py`
- Changed: `src/minimongodb/bson/types.py`
- Changed: `src/minimongodb/bson/__init__.py`
- Changed: `src/minimongodb/index/id_index.py`
- Changed: `src/minimongodb/collection.py`

- Historical additions included bool/int and int/float boundary tests and confirm Python raw-key
  behavior fails them.
- The recorded implementation included recursive type-tagged canonical keys and use them in both
  batch pending-ID validation and `IdIndex`.
- Historical regression coverage included CRUD, BSON, oplog, and recovery tests.

### Milestone 3: Checkpoint and documentation

**Recorded file scope:**
- Changed: `tests/test_storage.py`
- Changed: `src/minimongodb/storage/checkpoint.py`
- Changed: `docs/DIFFERENCES.md`
- Changed: `docs/mapping.md`
- Changed: `docs/zh/DIFFERENCES.md`
- Changed: `docs/zh/mapping.md`

- Historical additions included a test proving a directory file descriptor is fsynced after rename.
- Historical additions included the parent-directory fsync.
- The recorded documentation covered batch partial failure and journal-first publication in English
  and Chinese.
- Classify top-level `$not` as a Semantically opposite project extension
  in both languages, without translating the rest of `docs/zh/mapping.md`.

### Milestone 4: Final verification

- Historical verification covered the named focused checks.
- Historical verification covered the named focused checks.
- Historical verification covered the named focused checks.
- Historical acceptance reporting included the injection matrix and exact test count; no commit was part of the task.
