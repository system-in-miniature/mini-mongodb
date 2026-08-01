# Stage 02 · Array-aware query matching / 数组感知的查询匹配

<!-- journey: chapter=3 tests_added=2 -->

## English

### Goal

Build array-aware query matching and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `src/minimongodb/query/__init__.py`
- `src/minimongodb/query/matcher.py`
- `tests/test_array_matching.py`
- `tests/test_query.py`

### The problem at this point

Dotted paths and arrays make a query document ambiguous unless scalar element matching and exact compound-value equality are separated.

### Test contract

#### See the failure first

The counterexamples compare scalar-to-array matching, literal array order, exact embedded documents, dotted traversal, logical branches, and unknown operators.

<!-- journey-file: tests/test_array_matching.py -->
<!-- journey-file: tests/test_query.py -->
#### Array-aware query matching test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The counterexamples compare scalar-to-array matching, literal array order, exact embedded documents, dotted traversal, logical branches, and unknown operators.

##### Key test statement

```python
assert matches({"tags": ["database", "python"]}, {"tags": "python"})
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

A query is a recursive predicate tree. Field resolution may fan out through arrays, while a literal list or document remains one exact BSON value.

### Why this mechanism is necessary

Dotted paths and arrays make a query document ambiguous unless scalar element matching and exact compound-value equality are separated. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

The matcher resolves candidate values, applies field operators to them, and combines logical clauses without mutating the document.

### Mechanism blocks

<!-- journey-file: src/minimongodb/query/matcher.py -->
#### Array-aware query matching mechanism

##### What it is and why it appears

A query is a recursive predicate tree. Field resolution may fan out through arrays, while a literal list or document remains one exact BSON value.

##### Runtime role

The matcher resolves candidate values, applies field operators to them, and combines logical clauses without mutating the document.

##### Statement understanding

Keeping traversal and equality distinct prevents a partial embedded document from silently behaving like a dotted-field query.

<!-- journey-file: src/minimongodb/query/__init__.py -->
#### Package, fixture, and project support

These files only keep exports, test corpora, dependencies, and the runtime environment reproducible; they are supporting wiring rather than document-database mechanism logic.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/02-array-aware-queries/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

Keeping traversal and equality distinct prevents a partial embedded document from silently behaving like a dotted-field query.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 3](https://github.com/system-in-miniature/mini-mongodb/blob/main/docs/tutorial/03-queries.md)

## 中文

### 目标

实现数组感知的查询匹配，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `src/minimongodb/query/__init__.py`
- `src/minimongodb/query/matcher.py`
- `tests/test_array_matching.py`
- `tests/test_query.py`

### 当前遇到的问题

点路径与数组会让查询文档产生歧义，必须区分标量逐元素匹配与复合值精确相等。

### 测试契约

#### 先看会坏在哪里

反例比较标量对数组匹配、字面数组顺序、嵌入文档精确匹配、点路径展开、逻辑分支与未知算子。

<!-- journey-file: tests/test_array_matching.py -->
<!-- journey-file: tests/test_query.py -->
#### 数组感知的查询匹配测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

反例比较标量对数组匹配、字面数组顺序、嵌入文档精确匹配、点路径展开、逻辑分支与未知算子。

##### 关键测试语句

```python
assert matches({"tags": ["database", "python"]}, {"tags": "python"})
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

查询是递归谓词树。字段解析可以穿过数组展开，而字面 List 或 Document 仍是一个精确 BSON 值。

### 为什么需要这个机制

点路径与数组会让查询文档产生歧义，必须区分标量逐元素匹配与复合值精确相等。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Matcher 解析候选值、对它们应用字段算子，再组合逻辑子句，全程不修改文档。

### 机制板块

<!-- journey-file: src/minimongodb/query/matcher.py -->
#### 数组感知的查询匹配机制

##### 是什么，为什么现在需要

查询是递归谓词树。字段解析可以穿过数组展开，而字面 List 或 Document 仍是一个精确 BSON 值。

##### 在运行时做什么

Matcher 解析候选值、对它们应用字段算子，再组合逻辑子句，全程不修改文档。

##### 关键语句理解

把遍历与相等分开，可防止部分嵌入文档悄悄变成点字段查询。

<!-- journey-file: src/minimongodb/query/__init__.py -->
#### 包、Fixture 与工程支撑

这些文件只保持包导出、测试语料、依赖与运行环境可复现，不把支撑接线误讲成文档数据库机制。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/02-array-aware-queries/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

把遍历与相等分开，可防止部分嵌入文档悄悄变成点字段查询。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 3 章](https://github.com/system-in-miniature/mini-mongodb/blob/main/docs/zh/tutorial/03-queries.md)
