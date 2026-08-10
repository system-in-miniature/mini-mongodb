> **语言**: [English](README.md) | 简体中文

# MiniMongoDB

[![CI](https://github.com/system-in-miniature/mini-mongodb/actions/workflows/ci.yml/badge.svg)](https://github.com/system-in-miniature/mini-mongodb/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) ![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue.svg)

MiniMongoDB 是第七个**微型系统（System-in-Miniature）**项目：一个使用 Python
编写、具备确定性（deterministic）且以单进程（single-process）运行的文档
数据库内核（document database kernel）。它是教学模型，并非与
MongoDB 兼容的服务器——不提供线路协议（wire protocol）、JavaScript shell、
副本集（replica set），也不声称完全兼容 BSON/MQL。

M2 数据路径（data path）足够小，可以端到端地检查：

```text
Python dict/list document
→ dotted-path resolver
→ query matcher (including array element matching)
→ update or replacement routing
→ automatic _id plus secondary/compound multikey indexes
→ COLLSCAN/IXSCAN planner and explain counters
→ idempotent post-image oplog
→ CRC journal + checkpoint
→ startup recovery
```

核心课程是一个经常让 SQL 用户感到意外的 MongoDB 行为：

```python
from minimongodb import Collection

people = Collection("people")
people.insert_one(
    {
        "name": "Ada",
        "tags": ["database", "python"],
        "profile": {"city": "London", "role": "engineer"},
    }
)

assert people.find({"tags": "python"})       # scalar checks array elements
assert not people.find({"profile": {"city": "London"}})  # exact document
assert people.find({"profile.city": "London"})            # dotted field
```

## 快速开始

需要 Python 3.12 或更高版本，以及 [uv](https://docs.astral.sh/uv/)。
运行时代码没有第三方依赖；开发依赖组中只有 pytest。

```bash
uv sync
uv run pytest -q
uv run python labs/lab_array_matching.py
uv run python labs/lab_oplog_idempotent.py
uv run python labs/lab_crash_recovery.py
uv run python labs/lab_multikey_index.py
uv run python labs/lab_explain.py
```

持久化使用需要从一个显式指定的目录开始：

```python
from minimongodb import Database

database = Database("./demo-data")
users = database.get_collection("users")
users.insert_one({"name": "Ada", "visits": 1})
users.update_one({"name": "Ada"}, {"$inc": {"visits": 1}})
database.checkpoint()

restarted = Database("./demo-data")
print(restarted["users"].find())
```

所有返回的文档都是副本。数据库拥有其存储值，因此调用者无法通过修改结果
字典来改变持久化数据。

## M2 及之前已实现内容

- 嵌套的 dict/list 值、由计数器支持的确定性 `ObjectId`、显式类型标签，以及
  有文档说明的简化跨类型顺序；
- 点分路径（dotted path）读取和更新，包括数字数组索引；
- 单条或多条的插入、查询、更新、替换和删除 API；
- `$eq`（隐式或显式）、`$gt/$gte/$lt/$lte/$ne/$in/$exists`、
  `$and/$or/$not`；
- 自动检查所存数组元素的标量谓词；
- `$set/$unset/$inc/$push/$pull`，以及不可变的 `_id`；
- 自动唯一 `_id` 索引和重复键失败；
- 基于点分路径的单字段与复合升序索引、带 BSON 标签的 canonical 键、数组
  multikey 展开，以及可选的唯一约束；
- 确定性的复合前缀选择性估计、COLLSCAN/IXSCAN 选择和 `explain` 扫描计数；
- `$match/$project/$group/$sort/$limit` 管道，以及
  `$sum/$avg/$min/$max/$push` 分组累加器；
- 按文档生成的操作日志（oplog）条目：将动作型更新改写为最终 `$set`
  后像（post-image），并支持幂等重放（idempotent replay）；
- 长度加 CRC 的日志帧（journal frame）、最终尾部修复、原子检查点快照
  （checkpoint snapshot），以及检查点加日志的启动恢复。

M3 的封顶操作日志（capped oplog）保留和复制映射尚未实现。索引定义会写入
journal 和 checkpoint；文档写入仍只在 journal 追加成功后才一起发布文档、
`_id` 索引和全部二级索引条目。

## 目录指南

```text
src/minimongodb/
  bson/        values, ObjectId, exact equality, ordering, dotted paths
  query/       logical operators and array-aware matching
  update/      replacement routing and update operators
  index/       unique _id plus canonical compound/multikey indexes
  oplog/       post-image entries and idempotent replay; capped.py is M3
  storage/     tagged codec, CRC journal, checkpoint, recovery inputs
  plan/        selectivity estimate, COLLSCAN/IXSCAN choice, explain plan
  aggregate/   match/project/group/sort/limit operator pipeline
  collection.py
  database.py
labs/          five executable, public-API experiments
tests/         mechanism-focused tests, including crash boundaries
docs/          real-system mapping and declared differences
```

## 与 MiniPostgres 对照阅读：关系与文档

阅读这两个项目时，可以沿着相同的问题追踪不同的数据模型：

| Question | MiniPostgres | MiniMongoDB |
|---|---|---|
| What is stored? | schema-typed rows in relations | self-shaped nested documents |
| How is a field selected? | bound column reference | dotted path with array traversal |
| How is a query expressed? | parsed SQL → plan tree | query document → matcher + IXSCAN/COLLSCAN plan |
| How is data changed? | row-oriented DML expressions | replacement or path update operators |
| What is identity? | declared PK/UNIQUE indexes | mandatory automatic `_id` index |
| What is the durable log? | physical/page-aware WAL | framed idempotent logical post-images |
| What is the key surprise? | NULL and three-valued logic | array auto-match vs exact document |

MiniPostgres 最适合从 SQL 解析开始，自顶向下经过规划和 Volcano 执行器来理解。
MiniMongoDB 则适合由内而外阅读：BSON 值/路径语义进入 matcher 与 canonical
multikey 索引，规划器再选择 Mongo 术语的 scan，聚合管道最后串接文档算子。
两者都暴露计划与算子流，但一个处理受 schema 约束的关系行，另一个始终保留
自描述的嵌套文档。

在把成功运行实验当作生产级 MongoDB 的证据之前，请阅读
[概念映射](docs/zh/mapping.md)和[已声明的差异](docs/zh/DIFFERENCES.md)。

## 可量化的机制证据

在选择率固定为 1% 的 100、1,000、10,000 文档夹具上，`kind_1` IXSCAN
相对 COLLSCAN 把 Docs Examined 稳定减少 100 倍。10,000 文档时由 10,000
降至 100，并且建索引前后的结果完全一致。这是确定性的 Explain 工作量计数，
不是耗时加速或生产 MongoDB 容量声明。证据见[中文协议](bench/PROTOCOL.zh-CN.md)、
[中文报告](bench/results/2026-08-10/report.zh-CN.md)与相邻原始 JSON。

## 商标声明

MiniMongoDB 是独立的教学项目，与 MongoDB, Inc. 无隶属、背书或赞助关系。"MongoDB" 商标归其所有者所有。
