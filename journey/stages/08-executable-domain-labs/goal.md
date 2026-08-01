# Stage 08 · Executable domain experiments / 可执行领域实验

<!-- journey: chapter=10 tests_added=1 -->

## English

### Goal

Build executable domain experiments and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

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

<!-- journey-file: tests/test_labs.py -->
#### Executable domain experiments test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The lab contract starts each script in a fresh process and checks visible markers for array semantics, idempotence, crash recovery, multikey expansion, and plan changes.

##### Key test statement

```python
assert all(marker in completed.stdout for marker in markers)
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

A lab is a small end-to-end observation surface built only from exported APIs; it connects internal invariants to behavior a learner can reproduce.

### Why this mechanism is necessary

Individual unit contracts do not show whether the public API can demonstrate the complete document-database mechanisms as runnable experiments. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

Each process constructs one counterexample, prints the important before-and-after state, and exits without relying on private fixtures or prior data.

### Mechanism blocks

<!-- journey-file: labs/lab_array_matching.py -->
<!-- journey-file: labs/lab_crash_recovery.py -->
<!-- journey-file: labs/lab_explain.py -->
<!-- journey-file: labs/lab_multikey_index.py -->
<!-- journey-file: labs/lab_oplog_idempotent.py -->
#### Executable domain experiments mechanism

##### What it is and why it appears

A lab is a small end-to-end observation surface built only from exported APIs; it connects internal invariants to behavior a learner can reproduce.

##### Runtime role

Each process constructs one counterexample, prints the important before-and-after state, and exits without relying on private fixtures or prior data.

##### Statement understanding

Fresh-process execution closes the domain loop: imports, public ownership, persistence, and observable terminology must work together.



### Verification evidence

Run `uv run pytest -q $(cat journey/stages/08-executable-domain-labs/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

Fresh-process execution closes the domain loop: imports, public ownership, persistence, and observable terminology must work together.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 10](https://github.com/system-in-miniature/mini-mongodb/blob/main/docs/tutorial/10-relational-vs-document.md)

## 中文

### 目标

实现可执行领域实验，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

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

<!-- journey-file: tests/test_labs.py -->
#### 可执行领域实验测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

Lab 契约在新进程中启动每个脚本，并检查数组语义、幂等、崩溃恢复、多键展开与计划变化的可见标记。

##### 关键测试语句

```python
assert all(marker in completed.stdout for marker in markers)
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

Lab 是只使用导出 API 的小型端到端观察面，把内部不变量连接到学习者可复现的行为。

### 为什么需要这个机制

单个单元契约无法说明公共 API 是否能把完整文档数据库机制展示成可运行实验。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

每个进程构造一个反例、打印关键前后状态，并且不依赖私有 Fixture 或已有数据即可退出。

### 机制板块

<!-- journey-file: labs/lab_array_matching.py -->
<!-- journey-file: labs/lab_crash_recovery.py -->
<!-- journey-file: labs/lab_explain.py -->
<!-- journey-file: labs/lab_multikey_index.py -->
<!-- journey-file: labs/lab_oplog_idempotent.py -->
#### 可执行领域实验机制

##### 是什么，为什么现在需要

Lab 是只使用导出 API 的小型端到端观察面，把内部不变量连接到学习者可复现的行为。

##### 在运行时做什么

每个进程构造一个反例、打印关键前后状态，并且不依赖私有 Fixture 或已有数据即可退出。

##### 关键语句理解

新进程执行闭合领域回路：导入、公共所有权、持久化与可观察术语必须协同工作。



### 验证证据

运行 `uv run pytest -q $(cat journey/stages/08-executable-domain-labs/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

新进程执行闭合领域回路：导入、公共所有权、持久化与可观察术语必须协同工作。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 10 章](https://github.com/system-in-miniature/mini-mongodb/blob/main/docs/zh/tutorial/10-relational-vs-document.md)
