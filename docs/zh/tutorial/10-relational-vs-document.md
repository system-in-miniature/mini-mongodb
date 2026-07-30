# 第 10 章：关系系统与文档系统

最后一章转换视角。我们不再增加机制，而是向关系微型系统与本文档微型
系统提出同一组工程问题：存储什么？名字怎样绑定？匹配在哪里发生？
索引拥有什么？哪些 operator 会阻塞？原子边界在哪里？目标不是宣称
某个模型更优，而是学会哪些假设可以安全迁移，哪些必须重新推导。

## 学习目标

学完本章，你将能够：

- 比较 schema-bound row 与 self-shaped nested document；
- 把 SQL binding/关系 plan operator 对应到点路径 matching 与文档
  pipeline stage；
- 对照 primary/unique index 与 MiniMongoDB 强制 `_id`、multikey
  ownership；
- 准确陈述 MiniMongoDB 的单文档和 batch 持久边界；
- 使用仓库 mapping 与 differences ledger，区分可迁移机制与教学简化。

## 10.1 存储模型：先看形状，再看算子

关系系统把 tuple 存在有声明 schema 的 relation 中。列名、类型、
nullability 与 constraint 在查询查看 row 前就具有 catalog 含义。
文档系统存储自带嵌套形状的 record。同一 collection 的两个文档可以有
不同字段或数组长度，所以 path resolution 与 missing value 仍是运行时
问题。

MiniMongoDB 在 `src/minimongodb/bson/types.py` 把这点具体化。
`clone_document` 验证并 deep-copy 支持的 Python `dict`/`list` tree；
`type_tag`、`bson_equal`、`canonical_key`、`bson_compare` 在没有
collection schema 时建立值身份与顺序。在
`src/minimongodb/bson/path.py` 中，`get_path` 动态解释点组件，遍历
字典与明确数组位置，路径不存在时返回 `MISSING`。

关系侧对应物是绑定后的 column reference：完成 parse/bind 后，operator
知道读取哪个 tuple slot 与声明类型。MiniMongoDB 的
`"customer.address.city"` 仍是逐文档计算的 value-level path。这种
灵活性适合演进的嵌套形状，却把部分失败与歧义从定义期移动到查询/
更新时间。

Identity 也不同。关系表可声明 primary key 与额外 unique constraint。
每个 MiniMongoDB `Collection` 都在 `Collection.__init__` 构造
`IdIndex`；`Collection.insert_many` 用注入 generator 填充缺失 `_id`。
自动索引是强制的，而微型系统甚至允许结构化 `_id`，因此需要 canonical
BSON-shaped key，而不是 scalar tuple column。

## 10.2 查询语言与 operator flow

关系路径通常是：

```text
SQL text → parser → binder/catalog → logical plan → physical operators
```

Predicate 消费 schema-bound expression；Volcano-style executor 让父
operator 从子节点 pull tuple。Selection、projection、join、aggregate、
sort 形成 plan tree。

MiniMongoDB 从 parse 之后开始，因为 API 已接收 Python query document。
`src/minimongodb/collection.py` 的 `Collection._run_query` 用 `matches`
验证 query document，调用 `choose_plan`，取得所有文档或索引候选 id，
最后再用 `matches` 过滤：

```text
query dict → IXSCAN/COLLSCAN candidate choice → matcher → cloned result list
```

较短的 frontend 不代表语义简单。
`src/minimongodb/query/matcher.py` 的 `matches` 拥有 array element
fan-out、literal whole-array/document equality、dotted selection、
missing/null distinction 和支持的 logical/comparison operator。这些
运行时值规则就是文档侧对关系 binding 与三值 predicate 语义的对应。

Aggregation 又增加 operator pipeline。
`src/minimongodb/aggregate/__init__.py` 的 `execute_pipeline` 组合文档
iterable。`$match/$project/$limit` 增量 pull，`$sort/$group` 阻塞并
物化。关系 `Filter`/`Project` 与文档 `$match/$project` 共享逐 record
转换思想；关系 `Sort`/`Aggregate` 与文档 `$sort/$group` 共享内存
边界。区别在被转换的 record：一个是列已绑定的固定 tuple，一个是用
点引用的自描述嵌套文档。

MiniMongoDB 没有 join stage。关系 normalized design 可能把 order 与
line item 分表再 join；文档设计可嵌入 line-item subdocument，使一个
order 能被整体读取，代价是重复与可能更大的 update unit。真实 MongoDB
提供 `$lookup`，本微型系统没有。

## 10.3 索引：row key 与 document fan-out

两个模型都用索引把有序 key 映射到 record identity，有序复合键也都依赖
最左前缀。MiniMongoDB 的 `SecondaryIndex.prefix_length` 与
`choose_plan` 让这个共同机制可见。

文档模型增加了 multikey ownership。
`src/minimongodb/index/secondary.py` 的
`SecondaryIndex._document_entries` 遍历点路径，递归展开数组 leaf，
计算复合笛卡尔积。一个文档因此可拥有多个 index key。传统 scalar
关系索引通常每 row 一个 key tuple；关系式表示 tags 往往使用 child
table，每个 tag 对应一行和一条 index entry。

这一区别改变 cardinality 推理。MiniMongoDB 的 `keysExamined` 数匹配
key bucket，`docsExamined` 数候选 owner。多个 key 可指向一个文档，
一个 key 也可指向多个文档。normalized child table 的规划器则推理
child row 以及回到 parent 的 join。

两个世界的 uniqueness 都应前瞻：发布前拒绝冲突 key。MiniMongoDB 在
`SecondaryIndex.validate_documents` 与 `validate_replace` 实现它。
但 missing 规则是项目特定的：missing 占类 null key，所以 unique
index 允许一个 missing/null owner。不要未经核实就把这个结果迁移到
SQL `NULL` uniqueness 或每种 MongoDB index option。

## 10.4 更新、日志与事务边界

关系系统通常暴露跨多个 statement/row 的 transaction，并带 isolation
与 rollback 规则。WAL 记录崩溃恢复需要的 storage change；生产数据库
还可能暴露 logical decoding 或 replication record。

MiniMongoDB 的边界更小。`Collection._update` 构造并验证副本，持久
emit 一条 post-image oplog entry，再用 `Collection._replace_at` 交换
文档及索引。单文档 mutation 只在一个 Python 进程内 atomic。它没有
并发读写隔离、MVCC、session、read/write concern 或多文档 transaction。

Batch 方法不会扩大边界。`insert_many` 整批验证 candidate，却逐文档
emit 与 publish。`update_many/delete_many` 同样逐文档 commit。journal
失败会留下更早的 durable prefix，并保持后续 item 未变。这与把关系
多行 statement 包在一个 ACID transaction 内差别显著。

日志设计也不同。`Collection._post_image_update` 把 `$inc` 等动作改写
为最终 `$set` 值。`Oplog.emit` 在发布序号前把逻辑记录发给 journal
listener。真实 MongoDB 分离 WiredTiger recovery journal 与 replica-set
oplog；MiniMongoDB 有意用同一逻辑记录为本地恢复做 frame。

`src/minimongodb/database.py` 的 `Database.__init__` 加载 checkpoint
与 journal state，恢复文档/索引定义，并只在 checkpoint sequence 后
调用 `replay`。`Database.checkpoint` 写完整 database snapshot 与当前
durable sequence。这与许多系统“snapshot + newer log”的宽泛恢复形状
相似，却不是 page-oriented relational WAL 或 WiredTiger checkpoint。

## 10.5 实用对照矩阵

| 问题 | 关系微型系统 / MiniPostgres 视角 | MiniMongoDB |
|---|---|---|
| 存储单位 | Relation 中的 schema-typed row | Self-shaped nested document |
| 名称解析 | 绑定后的表/列引用 | 运行时点路径 |
| 查询表面 | Parsed SQL expression | Python query document / MQL 子集 |
| 物理访问 | 行/索引上的 scan operator | `COLLSCAN` 或 `IXSCAN` 候选 |
| 组合方式 | Plan tree，父节点 pull tuple | 有序文档 stage pipeline |
| 重复数据 | Child table 产生更多 row | Array 产生 multikey fan-out |
| Identity | 声明 PK/UNIQUE | 强制自动 `_id_` |
| 阻塞工作 | Sort/aggregate 拥有输入 | `$sort/$group` 拥有输入 |
| Update unit | 由 transaction 管理 | 每条 durable entry 一个复制文档 |
| 恢复日志 | 面向关系 storage 的 WAL | 带 frame 的逻辑 post-image entry |

该矩阵是阅读指南，不是 compatibility claim。用它提出相同 ownership
问题：谁验证值？谁选择候选？谁拥有中间状态？何时变更持久？什么可以
重试？

## 10.6 与真实系统对照

真实 PostgreSQL 家族系统还加入 catalog、SQL parsing/binding、join、
constraint、复杂 optimizer、MVCC、lock、transaction isolation、page
storage、WAL、vacuum、replication 等。真实 MongoDB 还加入 binary BSON、
wire protocol/driver、storage-engine page/cache/checkpoint、replica set、
sharding、transaction、concern、丰富 MQL/aggregation 与大量索引类型。

MiniMongoDB 是 deterministic single-process kernel，不是 server。它没有
wire protocol、authentication、concurrent isolation、multi-document
ACID、replication、sharding、`$lookup` 或完整 BSON/MQL。它最有力的
课程是本地机制：BSON-shaped equality、path/array matching、canonical
multikey ownership、candidate planning、post-image convergence 与
durability-before-publication。

推广任何行为前先查阅
[与 MongoDB 的差异](../DIFFERENCES.md)，再使用
[关系算子与文档管道](../mapping.md#关系算子与文档管道)和
[映射表的级别标签](../mapping.md)：“等价”命名一个 invariant，
“有意简化”缩小 machinery，“语义相反”则警告不要类比。这种证据纪律
正是 System-in-Miniature 系列要教授的方法。

## 10.7 动手实验：用三种方式读取一个嵌入形状

运行：

```bash
UV_CACHE_DIR=/tmp/minimongodb-uv-cache uv run python - <<'PY'
from minimongodb import Collection
orders = Collection("orders")
orders.insert_many([
    {"_id": 1, "customer": {"name": "Ada"}, "items": [{"sku": "PEN"}, {"sku": "BOOK"}], "total": 12},
    {"_id": 2, "customer": {"name": "Lin"}, "items": [{"sku": "PEN"}], "total": 4},
])
print("dotted query:", [d["_id"] for d in orders.find({"customer.name": "Ada"})])
print("array fan-out:", [d["_id"] for d in orders.find({"items.sku": "PEN"})])
print("grouped:", orders.aggregate([{"$group": {"_id": None, "revenue": {"$sum": "$total"}}}]))
PY
```

实测输出：

```text
dotted query: [1]
array fan-out: [1, 2]
grouped: [{'_id': None, 'revenue': 16}]
```

关系表示通常把 orders/items 分开，用 schema 绑定 column，并对 row 做
join 或 aggregate。该输出并不证明哪种布局更好，只让 embedded
document 的运行时 path 与 array 语义可见。

运行跨机制合同：

```bash
UV_CACHE_DIR=/tmp/minimongodb-uv-cache uv run pytest -q tests/test_query.py tests/test_aggregate.py tests/test_indexes.py
```

实测输出：

```text
................................                                         [100%]
32 passed in 0.13s
```

这些命令不使用 socket，只验证 MiniMongoDB 行为。若要与 live PostgreSQL
或 MongoDB service 对比，则属于“需运行时验证”，本文没有声称已验证。

## 10.8 练习

### 理解题 1：建模 tags

比较 embedded `tags` array 与关系 `article_tags` child table。重复出现
在哪里？index entry 标识什么？

??? note "参考答案"
    文档模型中，重复位于一个文档内，multikey index 把每个展开 tag
    key 映回同一文档 `_id`。normalized 关系模型中，重复位于独立 child
    row；索引标识这些 row，到达 article 可能需要 join。

### 理解题 2：原子性声明

`insert_many` 成功通过 validation，能否描述为 multi-document
transaction？

??? note "参考答案"
    不能。validation 是 batch-wide，但 durable emit 与 publication
    逐文档发生；失败会保留已提交前缀。没有 rollback、isolation 或
    multi-document ACID 边界。

### 动手题 3：建立关系式 projection

不改变 `src/`，写临时脚本，把实验中的 embedded orders 转为扁平
`(order_id, customer_name, sku)` tuple。验收：输出按确定顺序包含三条
tuple，order 1 保留两行。

??? note "参考答案"
    一种直接 API 解法：

    ```python
    rows = [
        (order["_id"], order["customer"]["name"], item["sku"])
        for order in orders.find()
        for item in order["items"]
    ]
    assert rows == [
        (1, "Ada", "PEN"),
        (1, "Ada", "BOOK"),
        (2, "Lin", "PEN"),
    ]
    ```

    comprehension 执行 application-side unnest analogue。真实关系执行与
    MongoDB `$unwind` 有更丰富的规划与语义；验收只检查 shape transform。

## 小结

关系与文档系统共享 typed identity、candidate access、operator
composition、blocking state、uniqueness、durable log 等深层机制，却把
它们放在不同 record shape 与 atomicity contract 周围。MiniMongoDB 的
价值在于每条边界都能从 Python document 一直追踪到 matching、indexing、
planning、post-image logging 与 recovery。带到真实系统中的持久习惯是：
迁移类比前，先检查 ownership 与 evidence。
