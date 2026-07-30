# MiniMongoDB M2 Implementation Plan

> **For agentic workers:** Execute inline with strict RED/GREEN checks. Do not
> commit because the task explicitly requires an uncommitted handoff.

**Goal:** Add deterministic secondary indexes, query planning/explain, and the
minimum aggregation pipeline while preserving M1 canonical BSON keys and
journal-first publication.

**Architecture:** `SecondaryIndex` owns canonical compound/multikey entries and
unique validation. `Planner` compares prefix-compatible candidate counts and
returns a COLLSCAN or IXSCAN execution plan. `Collection` validates prospective
index mutations, emits the durable post-image journal entry, then publishes the
document and every in-memory index. Aggregation stages form an iterable
operator pipeline and reuse `query.matches`.

**Tech Stack:** Python 3.12, dataclasses, pytest, uv.

---

### Task 1: Secondary indexes and write-path maintenance

**Files:**
- Create: `tests/test_indexes.py`
- Create: `src/minimongodb/index/secondary.py`
- Modify: `src/minimongodb/index/__init__.py`
- Modify: `src/minimongodb/collection.py`

- [ ] Write tests for single, compound dotted-path, canonical, unique, and
  multikey behavior.
- [ ] Run `UV_CACHE_DIR=/tmp/minimongodb-uv-cache uv run pytest -q
  tests/test_indexes.py` and confirm missing `create_index` behavior fails.
- [ ] Implement canonical compound keys, per-document multikey de-duplication,
  batch/replace validation, and create/drop-free index registration.
- [ ] Wire insert/update/replace/delete publication after `oplog.emit`.
- [ ] Re-run the focused tests until green.

### Task 2: Planner and explain

**Files:**
- Create: `tests/test_planner.py`
- Replace: `src/minimongodb/plan/__init__.py`
- Modify: `src/minimongodb/collection.py`

- [ ] Write tests for COLLSCAN, selective IXSCAN, compound-prefix eligibility,
  deterministic tie-breaking, and scan counters.
- [ ] Run the planner tests and confirm the absent public API is the RED cause.
- [ ] Implement prefix extraction, candidate-count estimates, plan selection,
  indexed candidate execution, and Mongo-shaped explain output.
- [ ] Re-run planner tests and all index tests.

### Task 3: Aggregation operator pipeline

**Files:**
- Create: `tests/test_aggregate.py`
- Replace: `src/minimongodb/aggregate/__init__.py`
- Modify: `src/minimongodb/collection.py`
- Modify: `src/minimongodb/errors.py`

- [ ] Write tests for `$match/$project/$group/$sort/$limit`, all five group
  accumulators, dotted expressions, and malformed stages.
- [ ] Run the aggregate tests and confirm missing `aggregate` is the RED cause.
- [ ] Implement one iterable transformation per stage, canonical group
  identity, BSON ordering, and matcher reuse.
- [ ] Re-run focused aggregate tests.

### Task 4: Labs and bilingual documentation

**Files:**
- Create: `labs/lab_multikey_index.py`
- Create: `labs/lab_explain.py`
- Modify: `tests/test_labs.py`
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Modify: `docs/mapping.md`
- Modify: `docs/zh/mapping.md`
- Modify: `docs/DIFFERENCES.md`
- Modify: `docs/zh/DIFFERENCES.md`
- Modify: `docs/labs-guide.md`
- Modify: `docs/zh/labs-guide.md`
- Modify: `mkdocs.yml`

- [ ] Add lab marker tests first and observe missing-script RED failures.
- [ ] Add public-API-only deterministic labs.
- [ ] Document implemented M2 behavior, limitations, pipeline/Volcano mapping,
  relation/document contrast, and new lab commands in both languages.
- [ ] Add both labs to the MkDocs navigation and run each script.

### Task 5: Final verification

**Files:** all M2 changes.

- [ ] Run focused tests, then
  `UV_CACHE_DIR=/tmp/minimongodb-uv-cache uv run pytest -q`.
- [ ] Run `git diff --check`.
- [ ] Run both lab scripts and retain their output summaries.
- [ ] Count new production-module lines with `wc -l`.
- [ ] Inspect `git status --short` and confirm no commit was created.
