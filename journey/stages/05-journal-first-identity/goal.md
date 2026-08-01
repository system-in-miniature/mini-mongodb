# Stage 05 · Journal-first identity boundary / 日志优先与身份边界

<!-- journey: chapter=5 tests_added=4 -->

## English

### Goal

Build journal-first identity boundary and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `src/minimongodb/bson/__init__.py`
- `src/minimongodb/bson/types.py`
- `src/minimongodb/collection.py`
- `src/minimongodb/index/id_index.py`
- `src/minimongodb/oplog/entry.py`
- `src/minimongodb/storage/checkpoint.py`
- `src/minimongodb/storage/journal.py`
- `tests/test_crud.py`
- `tests/test_oplog.py`
- `tests/test_recovery.py`
- `tests/test_storage.py`

### The problem at this point

The first implementation exposed three crash edges: publishing before journal success, using non-canonical `_id` keys, and renaming a checkpoint without syncing its directory.

### Test contract

#### See the failure first

Failure injection interrupts open, write, and fsync for insert, update, and delete; identity cases compare bool, numbers, NaN, and nested BSON; filesystem spies require directory fsync.

<!-- journey-file: tests/test_crud.py -->
<!-- journey-file: tests/test_oplog.py -->
<!-- journey-file: tests/test_recovery.py -->
<!-- journey-file: tests/test_storage.py -->
#### Journal-first identity boundary test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

Failure injection interrupts open, write, and fsync for insert, update, and delete; identity cases compare bool, numbers, NaN, and nested BSON; filesystem spies require directory fsync.

##### Key test statement

```python
assert collection.find() == [{"_id": True}, {"_id": 1}]
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

Journal-first means the durable append is the commit point for each logical write. Canonical keys make index identity agree with BSON equality, and directory fsync makes rename durable.

### Why this mechanism is necessary

The first implementation exposed three crash edges: publishing before journal success, using non-canonical `_id` keys, and renaming a checkpoint without syncing its directory. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

The collection prepares new state without exposing it, appends and syncs the oplog entry, then mutates documents and indexes; failure leaves the prior visible state.

### Mechanism blocks

<!-- journey-file: src/minimongodb/bson/types.py -->
<!-- journey-file: src/minimongodb/collection.py -->
<!-- journey-file: src/minimongodb/index/id_index.py -->
<!-- journey-file: src/minimongodb/oplog/entry.py -->
<!-- journey-file: src/minimongodb/storage/checkpoint.py -->
<!-- journey-file: src/minimongodb/storage/journal.py -->
#### Journal-first identity boundary mechanism

##### What it is and why it appears

Journal-first means the durable append is the commit point for each logical write. Canonical keys make index identity agree with BSON equality, and directory fsync makes rename durable.

##### Runtime role

The collection prepares new state without exposing it, appends and syncs the oplog entry, then mutates documents and indexes; failure leaves the prior visible state.

##### Statement understanding

Ordering is the proof: moving publication before append can acknowledge state that restart cannot reconstruct.

<!-- journey-file: src/minimongodb/bson/__init__.py -->
#### Package, fixture, and project support

These files only keep exports, test corpora, dependencies, and the runtime environment reproducible; they are supporting wiring rather than document-database mechanism logic.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/05-journal-first-identity/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

Ordering is the proof: moving publication before append can acknowledge state that restart cannot reconstruct.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 5](https://github.com/system-in-miniature/mini-mongodb/blob/main/docs/tutorial/05-durability.md)

## 中文

### 目标

实现日志优先与身份边界，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `src/minimongodb/bson/__init__.py`
- `src/minimongodb/bson/types.py`
- `src/minimongodb/collection.py`
- `src/minimongodb/index/id_index.py`
- `src/minimongodb/oplog/entry.py`
- `src/minimongodb/storage/checkpoint.py`
- `src/minimongodb/storage/journal.py`
- `tests/test_crud.py`
- `tests/test_oplog.py`
- `tests/test_recovery.py`
- `tests/test_storage.py`

### 当前遇到的问题

第一版暴露三个崩溃边界：Journal 成功前发布、使用非规范 `_id` Key，以及替换 Checkpoint 后未同步目录。

### 测试契约

#### 先看会坏在哪里

故障注入在 Insert、Update、Delete 的 Open、Write、Fsync 处中断；身份用例比较 Bool、Number、NaN 与嵌套 BSON；文件系统探针要求目录 Fsync。

<!-- journey-file: tests/test_crud.py -->
<!-- journey-file: tests/test_oplog.py -->
<!-- journey-file: tests/test_recovery.py -->
<!-- journey-file: tests/test_storage.py -->
#### 日志优先与身份边界测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

故障注入在 Insert、Update、Delete 的 Open、Write、Fsync 处中断；身份用例比较 Bool、Number、NaN 与嵌套 BSON；文件系统探针要求目录 Fsync。

##### 关键测试语句

```python
assert collection.find() == [{"_id": True}, {"_id": 1}]
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

Journal-first 表示持久 Append 是每次逻辑写的提交点。Canonical Key 让索引身份与 BSON 相等一致，目录 Fsync 让 Rename 真正持久。

### 为什么需要这个机制

第一版暴露三个崩溃边界：Journal 成功前发布、使用非规范 `_id` Key，以及替换 Checkpoint 后未同步目录。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Collection 先准备但不暴露新状态，Append 并同步 Oplog Entry，最后修改文档与索引；失败时保留旧可见状态。

### 机制板块

<!-- journey-file: src/minimongodb/bson/types.py -->
<!-- journey-file: src/minimongodb/collection.py -->
<!-- journey-file: src/minimongodb/index/id_index.py -->
<!-- journey-file: src/minimongodb/oplog/entry.py -->
<!-- journey-file: src/minimongodb/storage/checkpoint.py -->
<!-- journey-file: src/minimongodb/storage/journal.py -->
#### 日志优先与身份边界机制

##### 是什么，为什么现在需要

Journal-first 表示持久 Append 是每次逻辑写的提交点。Canonical Key 让索引身份与 BSON 相等一致，目录 Fsync 让 Rename 真正持久。

##### 在运行时做什么

Collection 先准备但不暴露新状态，Append 并同步 Oplog Entry，最后修改文档与索引；失败时保留旧可见状态。

##### 关键语句理解

顺序本身就是证明：若把发布移到 Append 前，就可能确认一份重启无法重建的状态。

<!-- journey-file: src/minimongodb/bson/__init__.py -->
#### 包、Fixture 与工程支撑

这些文件只保持包导出、测试语料、依赖与运行环境可复现，不把支撑接线误讲成文档数据库机制。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/05-journal-first-identity/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

顺序本身就是证明：若把发布移到 Append 前，就可能确认一份重启无法重建的状态。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 5 章](https://github.com/system-in-miniature/mini-mongodb/blob/main/docs/zh/tutorial/05-durability.md)
