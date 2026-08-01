# Stage 04 · CRUD, updates, and recovery / CRUD、更新与恢复闭环

<!-- journey: chapter=6 tests_added=4 -->

## English

### Goal

Build crud, updates, and recovery and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `src/minimongodb/__init__.py`
- `src/minimongodb/aggregate/__init__.py`
- `src/minimongodb/collection.py`
- `src/minimongodb/database.py`
- `src/minimongodb/index/__init__.py`
- `src/minimongodb/index/id_index.py`
- `src/minimongodb/oplog/replay.py`
- `src/minimongodb/plan/__init__.py`
- `src/minimongodb/update/__init__.py`
- `src/minimongodb/update/operators.py`
- `tests/test_crud.py`
- `tests/test_oplog.py`
- `tests/test_recovery.py`
- `tests/test_update.py`

### The problem at this point

Value and storage primitives do not yet form a database: one owner must coordinate identity, matching, mutation, oplog post-images, checkpoints, and startup replay.

### Test contract

#### See the failure first

The suite probes duplicate and immutable ids, partial batches, copied results, dotted update operators, idempotent replay, and checkpoint-plus-journal restart.

<!-- journey-file: tests/test_crud.py -->
<!-- journey-file: tests/test_oplog.py -->
<!-- journey-file: tests/test_recovery.py -->
<!-- journey-file: tests/test_update.py -->
#### CRUD, updates, and recovery test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The suite probes duplicate and immutable ids, partial batches, copied results, dotted update operators, idempotent replay, and checkpoint-plus-journal restart.

##### Key test statement

```python
assert entry.payload is not None
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

Collection owns live documents and indexes; Database owns named collections and durability. Operator updates become final-state post-images before logging.

### Why this mechanism is necessary

Value and storage primitives do not yet form a database: one owner must coordinate identity, matching, mutation, oplog post-images, checkpoints, and startup replay. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

A write validates a candidate, allocates its sequence, records the durable transition, then publishes owned state. Startup loads a checkpoint and replays only newer entries.

### Mechanism blocks

<!-- journey-file: src/minimongodb/aggregate/__init__.py -->
<!-- journey-file: src/minimongodb/collection.py -->
<!-- journey-file: src/minimongodb/database.py -->
<!-- journey-file: src/minimongodb/index/id_index.py -->
<!-- journey-file: src/minimongodb/oplog/replay.py -->
<!-- journey-file: src/minimongodb/plan/__init__.py -->
<!-- journey-file: src/minimongodb/update/operators.py -->
#### CRUD, updates, and recovery mechanism

##### What it is and why it appears

Collection owns live documents and indexes; Database owns named collections and durability. Operator updates become final-state post-images before logging.

##### Runtime role

A write validates a candidate, allocates its sequence, records the durable transition, then publishes owned state. Startup loads a checkpoint and replays only newer entries.

##### Statement understanding

Logging final assignments rather than user commands makes replay idempotent and keeps repeated recovery from applying `$inc` twice.

<!-- journey-file: src/minimongodb/__init__.py -->
<!-- journey-file: src/minimongodb/index/__init__.py -->
<!-- journey-file: src/minimongodb/update/__init__.py -->
#### Package, fixture, and project support

These files only keep exports, test corpora, dependencies, and the runtime environment reproducible; they are supporting wiring rather than document-database mechanism logic.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/04-crud-update-recovery/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

Logging final assignments rather than user commands makes replay idempotent and keeps repeated recovery from applying `$inc` twice.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 6](https://github.com/system-in-miniature/mini-mongodb/blob/main/docs/tutorial/06-oplog.md)

## 中文

### 目标

实现CRUD、更新与恢复闭环，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `src/minimongodb/__init__.py`
- `src/minimongodb/aggregate/__init__.py`
- `src/minimongodb/collection.py`
- `src/minimongodb/database.py`
- `src/minimongodb/index/__init__.py`
- `src/minimongodb/index/id_index.py`
- `src/minimongodb/oplog/replay.py`
- `src/minimongodb/plan/__init__.py`
- `src/minimongodb/update/__init__.py`
- `src/minimongodb/update/operators.py`
- `tests/test_crud.py`
- `tests/test_oplog.py`
- `tests/test_recovery.py`
- `tests/test_update.py`

### 当前遇到的问题

值与存储原语还不是数据库：必须由一个所有者协调身份、匹配、修改、Oplog 后镜像、Checkpoint 与启动回放。

### 测试契约

#### 先看会坏在哪里

测试覆盖重复与不可变 `_id`、部分批次、返回值副本、点路径更新算子、幂等回放及 Checkpoint 加 Journal 重启。

<!-- journey-file: tests/test_crud.py -->
<!-- journey-file: tests/test_oplog.py -->
<!-- journey-file: tests/test_recovery.py -->
<!-- journey-file: tests/test_update.py -->
#### CRUD、更新与恢复闭环测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

测试覆盖重复与不可变 `_id`、部分批次、返回值副本、点路径更新算子、幂等回放及 Checkpoint 加 Journal 重启。

##### 关键测试语句

```python
assert entry.payload is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

Collection 拥有活文档与索引；Database 拥有命名集合与持久性。算子更新在写日志前变成最终状态后镜像。

### 为什么需要这个机制

值与存储原语还不是数据库：必须由一个所有者协调身份、匹配、修改、Oplog 后镜像、Checkpoint 与启动回放。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

写入先校验候选状态、分配序号、记录持久转换，再发布受控状态。启动时载入 Checkpoint，只回放更新的 Entry。

### 机制板块

<!-- journey-file: src/minimongodb/aggregate/__init__.py -->
<!-- journey-file: src/minimongodb/collection.py -->
<!-- journey-file: src/minimongodb/database.py -->
<!-- journey-file: src/minimongodb/index/id_index.py -->
<!-- journey-file: src/minimongodb/oplog/replay.py -->
<!-- journey-file: src/minimongodb/plan/__init__.py -->
<!-- journey-file: src/minimongodb/update/operators.py -->
#### CRUD、更新与恢复闭环机制

##### 是什么，为什么现在需要

Collection 拥有活文档与索引；Database 拥有命名集合与持久性。算子更新在写日志前变成最终状态后镜像。

##### 在运行时做什么

写入先校验候选状态、分配序号、记录持久转换，再发布受控状态。启动时载入 Checkpoint，只回放更新的 Entry。

##### 关键语句理解

记录最终赋值而非用户命令，使回放幂等，并避免重复恢复把 `$inc` 执行两次。

<!-- journey-file: src/minimongodb/__init__.py -->
<!-- journey-file: src/minimongodb/index/__init__.py -->
<!-- journey-file: src/minimongodb/update/__init__.py -->
#### 包、Fixture 与工程支撑

这些文件只保持包导出、测试语料、依赖与运行环境可复现，不把支撑接线误讲成文档数据库机制。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/04-crud-update-recovery/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

记录最终赋值而非用户命令，使回放幂等，并避免重复恢复把 `$inc` 执行两次。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 6 章](https://github.com/system-in-miniature/mini-mongodb/blob/main/docs/zh/tutorial/06-oplog.md)
