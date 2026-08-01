# Stage 07 · Query validation before planning / 规划前的查询校验

<!-- journey: chapter=3 tests_added=1 -->

## English

### Goal

Build query validation before planning and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `src/minimongodb/query/__init__.py`
- `src/minimongodb/query/matcher.py`
- `tests/test_query.py`

### The problem at this point

When validation occurs only while matching documents, an invalid query can appear valid on an empty collection or an index path with no candidate.

### Test contract

#### See the failure first

The regression asks both `find` and `explain` to execute a malformed `$in` against an empty collection and nests another malformed operand behind a logical branch.

<!-- journey-file: tests/test_query.py -->
#### Query validation before planning test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The regression asks both `find` and `explain` to execute a malformed `$in` against an empty collection and nests another malformed operand behind a logical branch.

##### Key test statement

```python
with pytest.raises(InvalidQueryError, match=r"\$in requires an array"):
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

Syntax validity is an input property, independent of data cardinality or the chosen access path. Validation therefore walks the complete query tree before planning.

### Why this mechanism is necessary

When validation occurs only while matching documents, an invalid query can appear valid on an empty collection or an index path with no candidate. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

Collection validates once at the public boundary; matcher can then evaluate candidates under the same recursively checked operator contract.

### Mechanism blocks

<!-- journey-file: src/minimongodb/query/matcher.py -->
#### Query validation before planning mechanism

##### What it is and why it appears

Syntax validity is an input property, independent of data cardinality or the chosen access path. Validation therefore walks the complete query tree before planning.

##### Runtime role

Collection validates once at the public boundary; matcher can then evaluate candidates under the same recursively checked operator contract.

##### Statement understanding

Moving validation ahead of plan selection makes the same malformed query fail for empty, scanned, and indexed collections.

<!-- journey-file: src/minimongodb/query/__init__.py -->
#### Package, fixture, and project support

These files only keep exports, test corpora, dependencies, and the runtime environment reproducible; they are supporting wiring rather than document-database mechanism logic.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/07-query-validation-regression/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

Moving validation ahead of plan selection makes the same malformed query fail for empty, scanned, and indexed collections.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 3](https://github.com/system-in-miniature/mini-mongodb/blob/main/docs/tutorial/03-queries.md)

## 中文

### 目标

实现规划前的查询校验，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `src/minimongodb/query/__init__.py`
- `src/minimongodb/query/matcher.py`
- `tests/test_query.py`

### 当前遇到的问题

若只在匹配文档时校验，非法查询会在空集合或无候选索引路径上看似合法。

### 测试契约

#### 先看会坏在哪里

回归测试让 `find` 与 `explain` 在空集合上执行错误 `$in`，并把另一错误操作数藏在逻辑分支后。

<!-- journey-file: tests/test_query.py -->
#### 规划前的查询校验测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

回归测试让 `find` 与 `explain` 在空集合上执行错误 `$in`，并把另一错误操作数藏在逻辑分支后。

##### 关键测试语句

```python
with pytest.raises(InvalidQueryError, match=r"\$in requires an array"):
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

语法有效性是输入属性，与数据量和访问路径无关，因此校验必须在规划前遍历完整查询树。

### 为什么需要这个机制

若只在匹配文档时校验，非法查询会在空集合或无候选索引路径上看似合法。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Collection 在公共边界统一校验；Matcher 随后按同一套递归检查过的算子契约评估候选。

### 机制板块

<!-- journey-file: src/minimongodb/query/matcher.py -->
#### 规划前的查询校验机制

##### 是什么，为什么现在需要

语法有效性是输入属性，与数据量和访问路径无关，因此校验必须在规划前遍历完整查询树。

##### 在运行时做什么

Collection 在公共边界统一校验；Matcher 随后按同一套递归检查过的算子契约评估候选。

##### 关键语句理解

把校验移到选计划之前，可让同一非法查询在空集合、扫描与索引集合上都一致失败。

<!-- journey-file: src/minimongodb/query/__init__.py -->
#### 包、Fixture 与工程支撑

这些文件只保持包导出、测试语料、依赖与运行环境可复现，不把支撑接线误讲成文档数据库机制。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/07-query-validation-regression/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

把校验移到选计划之前，可让同一非法查询在空集合、扫描与索引集合上都一致失败。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 3 章](https://github.com/system-in-miniature/mini-mongodb/blob/main/docs/zh/tutorial/03-queries.md)
