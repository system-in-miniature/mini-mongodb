# Stage 03 · Durable oplog frames / 持久化 Oplog 帧

<!-- journey: chapter=5 tests_added=1 -->

## English

### Goal

Build durable oplog frames and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `src/minimongodb/oplog/__init__.py`
- `src/minimongodb/oplog/capped.py`
- `src/minimongodb/oplog/entry.py`
- `src/minimongodb/storage/__init__.py`
- `src/minimongodb/storage/checkpoint.py`
- `src/minimongodb/storage/codec.py`
- `src/minimongodb/storage/journal.py`
- `src/minimongodb/storage/recovery.py`
- `tests/test_storage.py`

### The problem at this point

In-memory operations are not restartable until entries, bytes, frame boundaries, corruption handling, and checkpoint replacement are explicit.

### Test contract

#### See the failure first

Tests truncate the final frame, corrupt its CRC or an earlier frame, round-trip tagged values, and inspect atomic checkpoint replacement.

<!-- journey-file: tests/test_storage.py -->
#### Durable oplog frames test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

Tests truncate the final frame, corrupt its CRC or an earlier frame, round-trip tagged values, and inspect atomic checkpoint replacement.

##### Key test statement

```python
assert journal.read_entries(repair=True) == [_entry(1)]
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

An oplog entry is a deterministic state transition record; the codec makes values self-describing, the journal frames entries with length and CRC, and a checkpoint snapshots a prefix.

### Why this mechanism is necessary

In-memory operations are not restartable until entries, bytes, frame boundaries, corruption handling, and checkpoint replacement are explicit. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

Append encodes and fsyncs one frame. Recovery accepts complete frames, may trim only a damaged final tail, and combines them with the latest atomic checkpoint.

### Mechanism blocks

<!-- journey-file: src/minimongodb/oplog/capped.py -->
<!-- journey-file: src/minimongodb/oplog/entry.py -->
<!-- journey-file: src/minimongodb/storage/checkpoint.py -->
<!-- journey-file: src/minimongodb/storage/codec.py -->
<!-- journey-file: src/minimongodb/storage/journal.py -->
<!-- journey-file: src/minimongodb/storage/recovery.py -->
#### Durable oplog frames mechanism

##### What it is and why it appears

An oplog entry is a deterministic state transition record; the codec makes values self-describing, the journal frames entries with length and CRC, and a checkpoint snapshots a prefix.

##### Runtime role

Append encodes and fsyncs one frame. Recovery accepts complete frames, may trim only a damaged final tail, and combines them with the latest atomic checkpoint.

##### Statement understanding

Only the final incomplete frame is repairable; hiding corruption before later bytes would invent a history that was never durably ordered.

<!-- journey-file: src/minimongodb/oplog/__init__.py -->
<!-- journey-file: src/minimongodb/storage/__init__.py -->
#### Package, fixture, and project support

These files only keep exports, test corpora, dependencies, and the runtime environment reproducible; they are supporting wiring rather than document-database mechanism logic.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/03-durable-log-frames/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

Only the final incomplete frame is repairable; hiding corruption before later bytes would invent a history that was never durably ordered.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 5](https://github.com/system-in-miniature/mini-mongodb/blob/main/docs/tutorial/05-durability.md)

## 中文

### 目标

实现持久化 Oplog 帧，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `src/minimongodb/oplog/__init__.py`
- `src/minimongodb/oplog/capped.py`
- `src/minimongodb/oplog/entry.py`
- `src/minimongodb/storage/__init__.py`
- `src/minimongodb/storage/checkpoint.py`
- `src/minimongodb/storage/codec.py`
- `src/minimongodb/storage/journal.py`
- `src/minimongodb/storage/recovery.py`
- `tests/test_storage.py`

### 当前遇到的问题

内存操作只有在 Entry、字节、帧边界、损坏处理和 Checkpoint 替换都明确后，才能支持重启。

### 测试契约

#### 先看会坏在哪里

测试截断末尾帧、破坏末帧或中间帧 CRC、往返带标签值，并检查 Checkpoint 原子替换。

<!-- journey-file: tests/test_storage.py -->
#### 持久化 Oplog 帧测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

测试截断末尾帧、破坏末帧或中间帧 CRC、往返带标签值，并检查 Checkpoint 原子替换。

##### 关键测试语句

```python
assert journal.read_entries(repair=True) == [_entry(1)]
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

Oplog Entry 是确定性状态转换记录；Codec 让值自描述，Journal 用长度和 CRC 组帧，Checkpoint 快照化一个前缀。

### 为什么需要这个机制

内存操作只有在 Entry、字节、帧边界、损坏处理和 Checkpoint 替换都明确后，才能支持重启。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Append 编码并 Fsync 一个帧。恢复接受完整帧，只能裁掉损坏的最终尾部，并与最新原子 Checkpoint 合并。

### 机制板块

<!-- journey-file: src/minimongodb/oplog/capped.py -->
<!-- journey-file: src/minimongodb/oplog/entry.py -->
<!-- journey-file: src/minimongodb/storage/checkpoint.py -->
<!-- journey-file: src/minimongodb/storage/codec.py -->
<!-- journey-file: src/minimongodb/storage/journal.py -->
<!-- journey-file: src/minimongodb/storage/recovery.py -->
#### 持久化 Oplog 帧机制

##### 是什么，为什么现在需要

Oplog Entry 是确定性状态转换记录；Codec 让值自描述，Journal 用长度和 CRC 组帧，Checkpoint 快照化一个前缀。

##### 在运行时做什么

Append 编码并 Fsync 一个帧。恢复接受完整帧，只能裁掉损坏的最终尾部，并与最新原子 Checkpoint 合并。

##### 关键语句理解

只有最终不完整帧可修复；隐藏后面仍有字节的中间损坏，会虚构一段从未持久排序的历史。

<!-- journey-file: src/minimongodb/oplog/__init__.py -->
<!-- journey-file: src/minimongodb/storage/__init__.py -->
#### 包、Fixture 与工程支撑

这些文件只保持包导出、测试语料、依赖与运行环境可复现，不把支撑接线误讲成文档数据库机制。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/03-durable-log-frames/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

只有最终不完整帧可修复；隐藏后面仍有字节的中间损坏，会虚构一段从未持久排序的历史。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 5 章](https://github.com/system-in-miniature/mini-mongodb/blob/main/docs/zh/tutorial/05-durability.md)
