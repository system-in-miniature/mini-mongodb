# Stage 08 · Executable domain experiments

### Goal

Build executable domain experiments and explain its boundary from an executable counterexample, runtime state, and the critical statement.

??? note "Deliverable files"
    - `labs/lab_array_matching.py`
    - `labs/lab_crash_recovery.py`
    - `labs/lab_explain.py`
    - `labs/lab_multikey_index.py`
    - `labs/lab_oplog_idempotent.py`
    - `tests/test_labs.py`

### The problem at this point

Individual unit contracts do not show whether the public API can demonstrate the complete document-database mechanisms as runnable experiments.

### Test contract

#### See the failure first

The lab contract starts each script in a fresh process and checks visible markers for array semantics, idempotence, crash recovery, multikey expansion, and plan changes.

??? note "File diff: tests/test_labs.py"
    ```diff
    diff --git a/tests/test_labs.py b/tests/test_labs.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..ee90a0bf1e763aa62f8e64e9441863c664e8bd14
    --- /dev/null
    +++ b/tests/test_labs.py
    @@ -0,0 +1,49 @@
    +"""Labs must stay executable scripts built only on the public package API."""
    +
    +import os
    +import subprocess
    +import sys
    +from pathlib import Path
    +
    +import pytest
    +
    +ROOT = Path(__file__).parents[1]
    +
    +
    +@pytest.mark.parametrize(
    +    ("script", "markers"),
    +    [
    +        (
    +            "lab_array_matching.py",
    +            ["scalar array match", "literal nested document", "dotted path match"],
    +        ),
    +        (
    +            "lab_oplog_idempotent.py",
    +            ["requested $inc", "stored oplog payload", "same after replay twice: True"],
    +        ),
    +        (
    +            "lab_crash_recovery.py",
    +            ["before injected crash", "truncated journal tail", "recovered documents"],
    +        ),
    +        (
    +            "lab_multikey_index.py",
    +            ["one document", "index keys", "matched document ids"],
    +        ),
    +        (
    +            "lab_explain.py",
    +            ["before index: COLLSCAN", "after index: IXSCAN", "docs examined"],
    +        ),
    +    ],
    +)
    +def test_lab_runs_as_a_script(script: str, markers: list[str]) -> None:
    +    environment = os.environ.copy()
    +    environment["PYTHONPATH"] = str(ROOT / "src")
    +    completed = subprocess.run(
    +        [sys.executable, str(ROOT / "labs" / script)],
    +        cwd=ROOT,
    +        env=environment,
    +        check=True,
    +        capture_output=True,
    +        text=True,
    +    )
    +    assert all(marker in completed.stdout for marker in markers)
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The lab contract starts each script in a fresh process and checks visible markers for array semantics, idempotence, crash recovery, multikey expansion, and plan changes.

**Key test statement**

```python
assert all(marker in completed.stdout for marker in markers)
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

A lab is a small end-to-end observation surface built only from exported APIs; it connects internal invariants to behavior a learner can reproduce.

### Why this mechanism is necessary

Individual unit contracts do not show whether the public API can demonstrate the complete document-database mechanisms as runnable experiments. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

Each process constructs one counterexample, prints the important before-and-after state, and exits without relying on private fixtures or prior data.

### Mechanism blocks

#### Executable domain experiments mechanism

Each process constructs one counterexample, prints the important before-and-after state, and exits without relying on private fixtures or prior data.

??? note "File diff: labs/lab_array_matching.py"
    ```diff
    diff --git a/labs/lab_array_matching.py b/labs/lab_array_matching.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..8df4047132e26507209c105fc1dd319772c492a6
    --- /dev/null
    +++ b/labs/lab_array_matching.py
    @@ -0,0 +1,30 @@
    +"""Contrast array auto-matching with exact nested-document matching."""
    +
    +from minimongodb import Collection
    +
    +
    +def main() -> None:
    +    people = Collection("people")
    +    people.insert_one(
    +        {
    +            "_id": 1,
    +            "name": "Ada",
    +            "tags": ["database", "python"],
    +            "profile": {"city": "London", "role": "engineer"},
    +        }
    +    )
    +
    +    scalar = people.find({"tags": "python"})
    +    literal = people.find({"profile": {"city": "London"}})
    +    dotted = people.find({"profile.city": "London"})
    +
    +    print("scalar array match:", [doc["name"] for doc in scalar])
    +    print("  A scalar query inspects each stored array element automatically.")
    +    print("literal nested document:", [doc["name"] for doc in literal])
    +    print("  A document literal means exact whole-document equality; extra keys matter.")
    +    print("dotted path match:", [doc["name"] for doc in dotted])
    +    print("  A dotted path selects one nested field, so unrelated keys do not matter.")
    +
    +
    +if __name__ == "__main__":
    +    main()
    ```

??? note "File diff: labs/lab_crash_recovery.py"
    ```diff
    diff --git a/labs/lab_crash_recovery.py b/labs/lab_crash_recovery.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..9149d443d382fd95e6930d686b9b69b95d75e1ee
    --- /dev/null
    +++ b/labs/lab_crash_recovery.py
    @@ -0,0 +1,26 @@
    +"""Inject a torn journal tail and recover checkpoint plus valid frame prefix."""
    +
    +from tempfile import TemporaryDirectory
    +
    +from minimongodb import Database
    +
    +
    +def main() -> None:
    +    with TemporaryDirectory(prefix="minimongodb-lab-") as directory:
    +        database = Database(directory)
    +        events = database.get_collection("events")
    +        events.insert_one({"_id": 1, "state": "checkpointed"})
    +        database.checkpoint()
    +        events.insert_one({"_id": 2, "state": "torn-tail-write"})
    +        print("before injected crash:", events.find())
    +
    +        remaining = database.inject_journal_tail_truncation(3)
    +        print("truncated journal tail; remaining bytes:", remaining)
    +
    +        recovered = Database(directory)
    +        print("recovered documents:", recovered.get_collection("events").find())
    +        print("  The checkpoint survives; the incomplete final frame is discarded.")
    +
    +
    +if __name__ == "__main__":
    +    main()
    ```

??? note "File diff: labs/lab_explain.py"
    ```diff
    diff --git a/labs/lab_explain.py b/labs/lab_explain.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..31c0fbd4ccf4c2942da6344ffbe2b2822d902bb9
    --- /dev/null
    +++ b/labs/lab_explain.py
    @@ -0,0 +1,29 @@
    +"""Compare the same selective query before and after index construction."""
    +
    +from minimongodb import Collection
    +
    +
    +def main() -> None:
    +    events = Collection("events")
    +    events.insert_many(
    +        [
    +            {"_id": 1, "kind": "rare"},
    +            {"_id": 2, "kind": "common"},
    +            {"_id": 3, "kind": "common"},
    +            {"_id": 4, "kind": "common"},
    +        ]
    +    )
    +    query = {"kind": "rare"}
    +
    +    before = events.explain(query)
    +    print("before index:", before["queryPlanner"]["winningPlan"]["stage"])
    +    print("docs examined:", before["executionStats"]["docsExamined"])
    +
    +    events.create_index("kind")
    +    after = events.explain(query)
    +    print("after index:", after["queryPlanner"]["winningPlan"]["stage"])
    +    print("docs examined:", after["executionStats"]["docsExamined"])
    +
    +
    +if __name__ == "__main__":
    +    main()
    ```

??? note "File diff: labs/lab_multikey_index.py"
    ```diff
    diff --git a/labs/lab_multikey_index.py b/labs/lab_multikey_index.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..1ae2427841837bfee95946bd28cfb77c75971f06
    --- /dev/null
    +++ b/labs/lab_multikey_index.py
    @@ -0,0 +1,25 @@
    +"""Show how one array-bearing document contributes several index keys."""
    +
    +from minimongodb import Collection
    +
    +
    +def main() -> None:
    +    articles = Collection("articles")
    +    articles.insert_many(
    +        [
    +            {"_id": 1, "title": "Storage notes", "tags": ["database", "storage"]},
    +            {"_id": 2, "title": "Python notes", "tags": ["python", "database"]},
    +            {"_id": 3, "title": "Networks", "tags": ["networking"]},
    +        ]
    +    )
    +    index_name = articles.create_index("tags")
    +    metadata = articles.index_information()[index_name]
    +
    +    print("one document can contribute several multikey index entries")
    +    print("index keys:", metadata["entries"], "multikey:", metadata["multikey"])
    +    matched = articles.find({"tags": "database"})
    +    print("matched document ids:", [document["_id"] for document in matched])
    +
    +
    +if __name__ == "__main__":
    +    main()
    ```

??? note "File diff: labs/lab_oplog_idempotent.py"
    ```diff
    diff --git a/labs/lab_oplog_idempotent.py b/labs/lab_oplog_idempotent.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..0aecbe579581346cfd2e1a656995f6d0fe6f7cb0
    --- /dev/null
    +++ b/labs/lab_oplog_idempotent.py
    @@ -0,0 +1,28 @@
    +"""Show why an action update becomes a final assignment in the oplog."""
    +
    +from minimongodb import Collection, Oplog, replay
    +
    +
    +def main() -> None:
    +    source = Collection("counters")
    +    source.insert_one({"_id": "visits", "count": 2})
    +    requested = {"$inc": {"count": 3}}
    +    source.update_one({"_id": "visits"}, requested)
    +    update_entry = list(source.oplog)[-1]
    +
    +    print("requested $inc:", requested)
    +    print("stored oplog payload:", update_entry.payload)
    +    print("  Repeating $inc would add twice; repeating $set converges on count=5.")
    +
    +    target = Collection("counters", oplog=Oplog())
    +    replay(source.oplog, target)
    +    once = target.find()
    +    replay(source.oplog, target)
    +    twice = target.find()
    +    print("after one replay:", once)
    +    print("after two replays:", twice)
    +    print("same after replay twice:", once == twice)
    +
    +
    +if __name__ == "__main__":
    +    main()
    ```

**What it is and why it appears**

A lab is a small end-to-end observation surface built only from exported APIs; it connects internal invariants to behavior a learner can reproduce.

**Runtime role**

Each process constructs one counterexample, prints the important before-and-after state, and exits without relying on private fixtures or prior data.

**Statement understanding**

Fresh-process execution closes the domain loop: imports, public ownership, persistence, and observable terminology must work together.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/08-executable-domain-labs/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

#### Quantified planner evidence

The deterministic evidence harness repeats one 1%-selective query at 100,
1,000, and 10,000 documents. Building `kind_1` changes COLLSCAN into IXSCAN and
reduces documents examined by 100x at every scale; at 10,000 documents the
counter falls from 10,000 to 100 while the returned result list stays equal.
This is planner-work evidence, not elapsed-time speedup or production MongoDB
capacity.

### Durable takeaways

Fresh-process execution closes the domain loop: imports, public ownership, persistence, and observable terminology must work together.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 10](https://github.com/system-in-miniature/mini-mongodb/blob/main/docs/tutorial/10-relational-vs-document.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-mongodb/blob/main/journey/stages/08-executable-domain-labs/stage.patch)
