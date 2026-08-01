# MiniMongoDB: A Document Database in Miniature / 微缩文档数据库

[Chinese edition / 中文版](zh/index.md)

MiniMongoDB is a deterministic, single-process Python kernel for learning how
a document database owns values, matches arrays, applies atomic
single-document updates, makes writes durable, replays an oplog, maintains
multikey indexes, chooses query plans, and executes aggregation pipelines.

MiniMongoDB 是一个确定性的单进程 Python 内核，用来学习文档数据库如何拥有值、
匹配数组、执行单文档原子更新、持久化写入、重放 oplog、维护 multikey 索引、
选择查询计划并执行聚合管道。

This book follows mechanisms in dependency order. Each chapter anchors its
claims to concrete functions under `src/minimongodb/`, contrasts the miniature
with real MongoDB, includes a measured experiment, and ends with exercises
whose proposed source changes are not applied to `src/`.

本书按机制依赖顺序展开。每章都把论断锚定到 `src/minimongodb/` 下的具体函数，
对照真实 MongoDB，提供带实测输出的实验，并以练习收束；练习中的源码改动只以
提案形式呈现，不落到 `src/`。

## Learning modes / 学习模式

### Mechanism Tutorial / 机制教程

Use the existing ten chapters for concept-first study of document values,
queries, updates, durability, oplogs, indexes, planning, and aggregation. /
希望先建立概念与运行时心智模型时，按现有十章学习文档值、查询、更新、持久化、
Oplog、索引、规划与聚合。

### Self-Guided Rebuild / 自主重建

Use the [eight-stage Journey](journey/index.md) to understand each problem, test
contract, concept boundary, and grouped code diff in a browser. / 使用
[八阶段重建旅程](zh/journey/index.md)，在浏览器中理解每个问题、测试契约、概念边界
与按机制分组的代码差异。

### Agent-Guided Rebuild / Agent 带教

Use the [CLI guide](agent-guide.md) when you want Codex to interactively teach,
implement, and verify one Stage. / 希望由 Codex 互动讲解、实现并验收一个 Stage 时，
参照 [CLI 使用教程](zh/agent-guide.md)。

## Before you begin / 开始之前

You need Python 3.12+ and [uv](https://docs.astral.sh/uv/):

需要 Python 3.12+ 和 [uv](https://docs.astral.sh/uv/)：

```bash
git clone https://github.com/system-in-miniature/mini-mongodb.git
cd mini-mongodb
uv sync
uv run pytest -q
```

MiniMongoDB is an in-process teaching kernel, not a MongoDB-compatible server.
It has no MongoDB wire protocol or driver endpoint. Keep the
[mechanism mapping](mapping.md) and [differences](DIFFERENCES.md) open while
reading so that equivalent, simplified, and opposite behaviors stay separate.

MiniMongoDB 是进程内教学内核，不是 MongoDB 兼容服务器；它没有 MongoDB 线协议
或驱动端点。阅读时请同时参考[机制映射](mapping.md)与
[差异](DIFFERENCES.md)，始终把等价、有意简化和语义相反的行为分开。

## Book contents / 全书目录

1. [Meet MiniMongoDB / 认识 MiniMongoDB](tutorial/01-getting-started.md) — positioning,
   environment, the first `insert`/`find`, and the complete system map. /
   定位、环境、第一次 `insert`/`find` 和完整系统地图。
2. [The Document Model / 文档模型](tutorial/02-document-model.md) — BSON-shaped type
   tags, comparison order, typed identity, and dotted paths. / BSON 形状类型
   标签、比较序、带类型标识和点路径。
3. [Query Semantics / 查询语义](tutorial/03-queries.md) — operators and the crucial
   distinction among array fan-out, exact whole values, and dotted paths. /
   查询算子，以及数组展开、整体精确值、点路径之间的关键区别。
4. [Update Operators / 更新算子](tutorial/04-updates.md) — `$set/$inc/$push/$pull`,
   replacement updates, immutable `_id`, and copy-first atomicity. /
   `$set/$inc/$push/$pull`、替换更新、不可变 `_id` 和 copy-first 原子性。
5. [Durability and Recovery / 持久性与恢复](tutorial/05-durability.md) — journal-first
   publication, committed prefixes, checkpoints, and startup recovery. /
   journal-first 发布、committed prefix、checkpoint 和启动恢复。
6. [The Oplog / Oplog](tutorial/06-oplog.md) — post-image rewriting and why replaying
   `$inc` as `$set` makes recovery idempotent. / 后像改写，以及把 `$inc`
   重放为 `$set` 为什么能得到幂等恢复。
7. [Secondary Indexes / 二级索引](tutorial/07-secondary-indexes.md) — compound, unique,
   and multikey indexes built from canonical typed keys. / 由 canonical 类型键
   构建的 compound、unique 与 multikey 索引。
8. [Planning and Explain / 规划与 Explain](tutorial/08-planner-explain.md) — IXSCAN versus
   COLLSCAN, leftmost prefixes, selectivity, and scan counters. / IXSCAN 与
   COLLSCAN、最左前缀、选择性和扫描计数。
9. [Aggregation Pipelines / 聚合管道](tutorial/09-aggregation.md) —
   `$match/$project/$group/$sort/$limit` as streaming and blocking stages. /
   把 `$match/$project/$group/$sort/$limit` 理解为流式与阻塞 stage。
10. [Relational versus Document / 关系模型与文档模型](tutorial/10-relational-vs-document.md) — a
    systematic comparison with MiniPostgres and the limits of each model. /
    与 MiniPostgres 的系统对照，以及两种模型各自的边界。

## Reference material / 参考资料

Use the [repository README](https://github.com/system-in-miniature/mini-mongodb#readme)
for the implemented feature inventory and source directory guide. The
[mechanism mapping](mapping.md) is the parity ledger; the
[differences chapter](DIFFERENCES.md) is the semantic boundary; and the
[lab guide](labs-guide.md) collects runnable demonstrations. Construction-time
plans are retained in the [design history archive](superpowers/README.md), but
the tutorial, current source, and tests define behavior.

[仓库中文 README](https://github.com/system-in-miniature/mini-mongodb/blob/main/README.zh-CN.md)
给出已实现能力清单和源码目录导览；[机制映射](mapping.md)是 parity 账本；
[差异](DIFFERENCES.md)定义语义边界；[实验指南](labs-guide.md)汇集可运行演示。
建设期计划保留在[设计历史存档](superpowers/README.md)，但行为由教程、当前
源码和测试共同定义。
