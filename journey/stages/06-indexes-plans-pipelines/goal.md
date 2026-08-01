# Stage 06 · Indexed plans and aggregation pipelines / 索引计划与聚合管道

<!-- journey: chapter=8 tests_added=3 -->

## English

### Goal

Build indexed plans and aggregation pipelines and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `src/minimongodb/aggregate/__init__.py`
- `src/minimongodb/collection.py`
- `src/minimongodb/database.py`
- `src/minimongodb/errors.py`
- `src/minimongodb/index/__init__.py`
- `src/minimongodb/index/id_index.py`
- `src/minimongodb/index/secondary.py`
- `src/minimongodb/plan/__init__.py`
- `src/minimongodb/storage/recovery.py`
- `tests/test_aggregate.py`
- `tests/test_indexes.py`
- `tests/test_planner.py`

### The problem at this point

The M2 collection needs reusable access paths and staged document transformation, but both must preserve the same BSON and ownership semantics as a collection scan.

### Test contract

#### See the failure first

Tests combine multikey and compound indexes, selectivity and explain counters, plus match, project, group, BSON-aware sort, limit, and malformed pipeline stages.

<!-- journey-file: tests/test_aggregate.py -->
<!-- journey-file: tests/test_indexes.py -->
<!-- journey-file: tests/test_planner.py -->
#### Indexed plans and aggregation pipelines test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

Tests combine multikey and compound indexes, selectivity and explain counters, plus match, project, group, BSON-aware sort, limit, and malformed pipeline stages.

##### Key test statement

```python
assert entry.payload is not None
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

Indexes map canonical keys to candidates, plans choose COLLSCAN or IXSCAN explicitly, and an aggregation pipeline composes ordered streaming or blocking document operators.

### Why this mechanism is necessary

The M2 collection needs reusable access paths and staged document transformation, but both must preserve the same BSON and ownership semantics as a collection scan. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

Writes stage all index entries before publication; reads fetch and recheck planned candidates; aggregation then threads owned documents through each validated stage.

### Mechanism blocks

<!-- journey-file: src/minimongodb/aggregate/__init__.py -->
<!-- journey-file: src/minimongodb/collection.py -->
<!-- journey-file: src/minimongodb/database.py -->
<!-- journey-file: src/minimongodb/errors.py -->
<!-- journey-file: src/minimongodb/index/id_index.py -->
<!-- journey-file: src/minimongodb/index/secondary.py -->
<!-- journey-file: src/minimongodb/plan/__init__.py -->
<!-- journey-file: src/minimongodb/storage/recovery.py -->
#### Indexed plans and aggregation pipelines mechanism

##### What it is and why it appears

Indexes map canonical keys to candidates, plans choose COLLSCAN or IXSCAN explicitly, and an aggregation pipeline composes ordered streaming or blocking document operators.

##### Runtime role

Writes stage all index entries before publication; reads fetch and recheck planned candidates; aggregation then threads owned documents through each validated stage.

##### Statement understanding

Access paths never replace predicate rechecking, and pipeline order remains observable; these boundaries keep optimization from changing document semantics.

<!-- journey-file: src/minimongodb/index/__init__.py -->
#### Package, fixture, and project support

These files only keep exports, test corpora, dependencies, and the runtime environment reproducible; they are supporting wiring rather than document-database mechanism logic.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/06-indexes-plans-pipelines/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

Access paths never replace predicate rechecking, and pipeline order remains observable; these boundaries keep optimization from changing document semantics.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 8](https://github.com/system-in-miniature/mini-mongodb/blob/main/docs/tutorial/08-planner-explain.md)

## 中文

### 目标

实现索引计划与聚合管道，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `src/minimongodb/aggregate/__init__.py`
- `src/minimongodb/collection.py`
- `src/minimongodb/database.py`
- `src/minimongodb/errors.py`
- `src/minimongodb/index/__init__.py`
- `src/minimongodb/index/id_index.py`
- `src/minimongodb/index/secondary.py`
- `src/minimongodb/plan/__init__.py`
- `src/minimongodb/storage/recovery.py`
- `tests/test_aggregate.py`
- `tests/test_indexes.py`
- `tests/test_planner.py`

### 当前遇到的问题

M2 Collection 需要可复用访问路径与分阶段文档变换，但两者都必须保持与 Collection Scan 相同的 BSON 与所有权语义。

### 测试契约

#### 先看会坏在哪里

测试组合 Multikey 与 Compound Index、选择度与 Explain 计数，以及 Match、Project、Group、BSON 感知 Sort、Limit 和错误 Pipeline Stage。

<!-- journey-file: tests/test_aggregate.py -->
<!-- journey-file: tests/test_indexes.py -->
<!-- journey-file: tests/test_planner.py -->
#### 索引计划与聚合管道测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

测试组合 Multikey 与 Compound Index、选择度与 Explain 计数，以及 Match、Project、Group、BSON 感知 Sort、Limit 和错误 Pipeline Stage。

##### 关键测试语句

```python
assert entry.payload is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

索引把 Canonical Key 映射到 Candidate，Plan 显式选择 COLLSCAN 或 IXSCAN，Aggregation Pipeline 则组合有序的流式或阻塞文档算子。

### 为什么需要这个机制

M2 Collection 需要可复用访问路径与分阶段文档变换，但两者都必须保持与 Collection Scan 相同的 BSON 与所有权语义。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

写入在发布前暂存全部索引项；读取取回并重检计划候选；随后聚合把受控文档依次传过每个已校验 Stage。

### 机制板块

<!-- journey-file: src/minimongodb/aggregate/__init__.py -->
<!-- journey-file: src/minimongodb/collection.py -->
<!-- journey-file: src/minimongodb/database.py -->
<!-- journey-file: src/minimongodb/errors.py -->
<!-- journey-file: src/minimongodb/index/id_index.py -->
<!-- journey-file: src/minimongodb/index/secondary.py -->
<!-- journey-file: src/minimongodb/plan/__init__.py -->
<!-- journey-file: src/minimongodb/storage/recovery.py -->
#### 索引计划与聚合管道机制

##### 是什么，为什么现在需要

索引把 Canonical Key 映射到 Candidate，Plan 显式选择 COLLSCAN 或 IXSCAN，Aggregation Pipeline 则组合有序的流式或阻塞文档算子。

##### 在运行时做什么

写入在发布前暂存全部索引项；读取取回并重检计划候选；随后聚合把受控文档依次传过每个已校验 Stage。

##### 关键语句理解

访问路径不能取代谓词重检，Pipeline 顺序也必须可观察；这些边界防止优化改变文档语义。

<!-- journey-file: src/minimongodb/index/__init__.py -->
#### 包、Fixture 与工程支撑

这些文件只保持包导出、测试语料、依赖与运行环境可复现，不把支撑接线误讲成文档数据库机制。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/06-indexes-plans-pipelines/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

访问路径不能取代谓词重检，Pipeline 顺序也必须可观察；这些边界防止优化改变文档语义。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 8 章](https://github.com/system-in-miniature/mini-mongodb/blob/main/docs/zh/tutorial/08-planner-explain.md)
