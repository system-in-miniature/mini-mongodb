# Stage 08 · 可执行领域实验

### 目标

实现可执行领域实验，并能从可执行反例、运行时状态与关键语句解释其边界。

??? note "交付文件"
    - `labs/lab_array_matching.py`
    - `labs/lab_crash_recovery.py`
    - `labs/lab_explain.py`
    - `labs/lab_multikey_index.py`
    - `labs/lab_oplog_idempotent.py`
    - `tests/test_labs.py`

### 当前遇到的问题

单个单元契约无法说明公共 API 是否能把完整文档数据库机制展示成可运行实验。

### 测试契约

#### 先看会坏在哪里

Lab 契约在新进程中启动每个脚本，并检查数组语义、幂等、崩溃恢复、多键展开与计划变化的可见标记。

??? note "文件差异：tests/test_labs.py"
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

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

Lab 契约在新进程中启动每个脚本，并检查数组语义、幂等、崩溃恢复、多键展开与计划变化的可见标记。

**关键测试语句**

```python
assert all(marker in completed.stdout for marker in markers)
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

Lab 是只使用导出 API 的小型端到端观察面，把内部不变量连接到学习者可复现的行为。

### 为什么需要这个机制

单个单元契约无法说明公共 API 是否能把完整文档数据库机制展示成可运行实验。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

每个进程构造一个反例、打印关键前后状态，并且不依赖私有 Fixture 或已有数据即可退出。

### 机制板块

#### 可执行领域实验机制

每个进程构造一个反例、打印关键前后状态，并且不依赖私有 Fixture 或已有数据即可退出。

??? note "文件差异：labs/lab_array_matching.py"
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

??? note "文件差异：labs/lab_crash_recovery.py"
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

??? note "文件差异：labs/lab_explain.py"
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

??? note "文件差异：labs/lab_multikey_index.py"
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

??? note "文件差异：labs/lab_oplog_idempotent.py"
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

**是什么，为什么现在需要**

Lab 是只使用导出 API 的小型端到端观察面，把内部不变量连接到学习者可复现的行为。

**在运行时做什么**

每个进程构造一个反例、打印关键前后状态，并且不依赖私有 Fixture 或已有数据即可退出。

**关键语句理解**

新进程执行闭合领域回路：导入、公共所有权、持久化与可观察术语必须协同工作。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/08-executable-domain-labs/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

新进程执行闭合领域回路：导入、公共所有权、持久化与可观察术语必须协同工作。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 10 章](https://github.com/system-in-miniature/mini-mongodb/blob/main/docs/zh/tutorial/10-relational-vs-document.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-mongodb/blob/main/journey/stages/08-executable-domain-labs/stage.patch)
