# Stage 01 · BSON values and dotted paths / BSON 值与点路径

<!-- journey: chapter=2 tests_added=1 -->

## English

### Goal

Build bson values and dotted paths and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `pyproject.toml`
- `src/minimongodb/bson/__init__.py`
- `src/minimongodb/bson/path.py`
- `src/minimongodb/bson/types.py`
- `src/minimongodb/errors.py`
- `tests/test_bson.py`
- `uv.lock`

### The problem at this point

A document store cannot compare, copy, identify, or traverse arbitrary Python values without a closed value contract.

### Test contract

#### See the failure first

The tests use nested aliases, unsupported values, ordered documents, mixed numeric identities, and invalid list paths to expose accidental Python semantics.

<!-- journey-file: tests/test_bson.py -->
#### BSON values and dotted paths test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The tests use nested aliases, unsupported values, ordered documents, mixed numeric identities, and invalid list paths to expose accidental Python semantics.

##### Key test statement

```python
assert generator() == ObjectId(40)
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

MiniMongoDB's BSON subset defines owned document copies, explicit type tags, exact equality, total ordering, ObjectId generation, and dotted reads or writes.

### Why this mechanism is necessary

A document store cannot compare, copy, identify, or traverse arbitrary Python values without a closed value contract. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

Values are validated and copied at the boundary; path traversal then walks mappings and numeric list positions without leaking caller-owned state.

### Mechanism blocks

<!-- journey-file: src/minimongodb/bson/path.py -->
<!-- journey-file: src/minimongodb/bson/types.py -->
<!-- journey-file: src/minimongodb/errors.py -->
#### BSON values and dotted paths mechanism

##### What it is and why it appears

MiniMongoDB's BSON subset defines owned document copies, explicit type tags, exact equality, total ordering, ObjectId generation, and dotted reads or writes.

##### Runtime role

Values are validated and copied at the boundary; path traversal then walks mappings and numeric list positions without leaking caller-owned state.

##### Statement understanding

Canonical value semantics must precede indexes, matching, logging, and persistence because all four reuse the same notion of identity.

<!-- journey-file: pyproject.toml -->
<!-- journey-file: src/minimongodb/bson/__init__.py -->
<!-- journey-file: uv.lock -->
#### Package, fixture, and project support

These files only keep exports, test corpora, dependencies, and the runtime environment reproducible; they are supporting wiring rather than document-database mechanism logic.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/01-bson-document-paths/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

Canonical value semantics must precede indexes, matching, logging, and persistence because all four reuse the same notion of identity.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 2](https://github.com/system-in-miniature/mini-mongodb/blob/main/docs/tutorial/02-document-model.md)

## 中文

### 目标

实现BSON 值与点路径，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `pyproject.toml`
- `src/minimongodb/bson/__init__.py`
- `src/minimongodb/bson/path.py`
- `src/minimongodb/bson/types.py`
- `src/minimongodb/errors.py`
- `tests/test_bson.py`
- `uv.lock`

### 当前遇到的问题

文档存储若没有封闭的值契约，就无法可靠比较、复制、标识或遍历任意 Python 值。

### 测试契约

#### 先看会坏在哪里

测试用嵌套别名、不支持的值、有序文档、混合数值身份与非法数组路径，暴露偶然的 Python 语义。

<!-- journey-file: tests/test_bson.py -->
#### BSON 值与点路径测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

测试用嵌套别名、不支持的值、有序文档、混合数值身份与非法数组路径，暴露偶然的 Python 语义。

##### 关键测试语句

```python
assert generator() == ObjectId(40)
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

MiniMongoDB 的 BSON 子集定义受控文档副本、显式类型标签、精确相等、全序、ObjectId 生成和点路径读写。

### 为什么需要这个机制

文档存储若没有封闭的值契约，就无法可靠比较、复制、标识或遍历任意 Python 值。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

值在边界被校验和复制；随后路径遍历只沿 Mapping 与数字数组下标前进，不泄漏调用方状态。

### 机制板块

<!-- journey-file: src/minimongodb/bson/path.py -->
<!-- journey-file: src/minimongodb/bson/types.py -->
<!-- journey-file: src/minimongodb/errors.py -->
#### BSON 值与点路径机制

##### 是什么，为什么现在需要

MiniMongoDB 的 BSON 子集定义受控文档副本、显式类型标签、精确相等、全序、ObjectId 生成和点路径读写。

##### 在运行时做什么

值在边界被校验和复制；随后路径遍历只沿 Mapping 与数字数组下标前进，不泄漏调用方状态。

##### 关键语句理解

规范值语义必须先于索引、匹配、日志和持久化，因为四者复用同一套身份定义。

<!-- journey-file: pyproject.toml -->
<!-- journey-file: src/minimongodb/bson/__init__.py -->
<!-- journey-file: uv.lock -->
#### 包、Fixture 与工程支撑

这些文件只保持包导出、测试语料、依赖与运行环境可复现，不把支撑接线误讲成文档数据库机制。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/01-bson-document-paths/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

规范值语义必须先于索引、匹配、日志和持久化，因为四者复用同一套身份定义。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 2 章](https://github.com/system-in-miniature/mini-mongodb/blob/main/docs/zh/tutorial/02-document-model.md)
