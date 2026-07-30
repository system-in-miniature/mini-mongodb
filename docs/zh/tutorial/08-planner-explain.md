# 第 8 章：查询规划与阅读 `explain`

创建索引并不代表每个匹配查询都应该使用它。规划器必须先证明索引能保持
matcher 语义，再判断候选集合是否优于扫描 collection。MiniMongoDB
让两个选择都具有确定性，并用 MongoDB 风格的 `IXSCAN`/`COLLSCAN`
词汇暴露结果。

## 学习目标

学完本章，你将能够：

- 从 `Collection.explain` 经过 `Collection._run_query` 跟踪到
  `choose_plan`；
- 推导复合索引的哪些字段构成可用前缀；
- 解释候选计数成本模型及其确定性 tie-break；
- 区分 `keysExamined`、`docsExamined` 与 `nReturned`；
- 找出 multikey predicate 和根数组 `_id` 触发的正确性回退。

## 8.1 规划不能替代匹配

公开入口是 `src/minimongodb/collection.py` 的 `Collection.explain`。
它把 `None` 规范化为 `{}`，调用 `Collection._run_query`，再包装已选
计划与真实执行计数：

```python
return {
    "queryPlanner": {"winningPlan": plan.summary(normalized)},
    "executionStats": {
        "nReturned": len(documents),
        "keysExamined": keys_examined,
        "docsExamined": docs_examined,
    },
}
```

`find`、`find_one` 与 `count_documents` 使用同一个 `_run_query`；
explain 不是另一套模拟。选择计划前，`_run_query` 调用
`matches({}, normalized)`。`matches` 会先调用独立的 `validate_query`，
在任何依赖文档的匹配之前递归检查完整算子结构。因此这个看似奇怪的空文档调用，
即使在 collection 为空或索引产生零候选时，也能完整验证查询语法。

计划只提供候选来源。collection scan 的 `candidates` 是保持插入顺序的
文档列表；index scan 的计划则提供 canonical 文档 id。由于 index
ownership bucket 是 set，`_run_query` 会遍历原 storage list，只保留
id 位于集合中的文档，再对每个候选调用 `matches`。

由此得到两个不变量。第一，索引不能改变查询语义：matcher 仍是最终
权威。第二，索引不能改变公开结果顺序：`find` 仍按插入顺序返回 eager
list。索引缩小工作量，但不定义结果顺序。

## 8.2 Plan 对象

`src/minimongodb/plan/__init__.py` 定义了冻结 dataclass `Plan`。核心
字段是 `stage`、可选 `index`、`prefix_length`、`candidate_ids` 与
`keys_examined`。没有索引时，`Plan.summary` 返回
`{"stage": "COLLSCAN"}`；二级索引计划还加入索引名、完整 key pattern
与可用前缀的 bound。

自动 `_id_` index 没有对应 `SecondaryIndex` 实例，所以
`choose_plan` 构造 `summary_override`。精确 `_id`、`$eq` 与 `$in`
可以通过 `IdIndex.get` 直接映射值。结果计划报告熟悉的 `_id_` 名称、
`{"_id": 1}` key pattern 与查询 bound。

`Plan` 保存候选 id 而不是候选文档。这让规划只负责身份与成本，而把
storage order、clone 与最终 matching 留给 `Collection`。

## 8.3 有意缩小的成本模型

`choose_plan` 向每个二级索引请求
`SecondaryIndex.prefix_length(query)`。没有可用最左前缀的索引被忽略。
每个可用索引再运行 `SecondaryIndex.scan`，返回候选 owner set 与扫描
过的匹配不同 index key 数。

候选按以下 tuple 排名：

1. 更少的候选文档 owner；
2. 更长的可用复合前缀（用负长度表示）；
3. 字典序更小的索引名。

这些 tie-break 让相同状态与查询每次选择同一计划，不需要随机 trial
execution 或随时间变化的 sampling。选出最佳索引后，规划器仍比较
候选数与 collection 总文档数。estimate 大于等于文档数时返回
`COLLSCAN`。因此不 selective 的索引即使技术上可用也会输。

这个 estimate 对当前内存 ownership set 是精确的，但不是生产成本
模型。它不了解 disk page、cache residency、index height、fetch cost、
CPU、sort satisfaction、projection 或历史统计。它的目的在于显示
决策边界：先判断语义资格，再估算减少量。

即使 query 与 index definition 不变，plan choice 也会随数据改变。
如果 `kind == "rare"` 从一个 owner 增长到全部 owner，同一个 `kind_1`
index 会从获胜 `IXSCAN` 变成 `COLLSCAN`。这是预期行为：规划器从当前
ownership bucket 推导 candidate cardinality。确定性表示相同状态产生
相同决策，不表示一个查询永久绑定某个 stage。由于没有 plan cache，
每次调用都会重新计算这个小型选择。

## 8.4 阅读三个计数

`nReturned` 是通过完整 matcher 的候选数；`docsExamined` 是送入 matcher
的候选文档数。对于 secondary index，`keysExamined` 是 scan 访问的匹配
distinct key bucket 数；自动 `_id_` fast path 使用另一种单位：它统计 lookup
probe，标量 equality 操作数计一次，`$in` array 中每个值各计一次，重复值和
不存在的值也照计。collection scan 没读索引，所以 key 数为零。

四个文档中只有一个满足 `kind == "rare"` 时：

- 建索引前，`COLLSCAN` 为 `keysExamined=0`、`docsExamined=4`、
  `nReturned=1`；
- 建立 selective `kind_1` 后，`IXSCAN` 为 `keysExamined=1`、
  `docsExamined=1`、`nReturned=1`。

不要假设 `keysExamined == docsExamined`。一个 key bucket 可以有多个
文档 owner，复合或 range scan 也可访问多个 key。也不要把
`nReturned/docsExamined` 当成完整成本；它只是可观察教学比率，不是
latency。

## 8.5 正确性驱动的回退

规划器包含两个特别有教学价值的逃生口。

第一，MiniMongoDB 允许根数组作为 `_id`，尽管这不是可迁移的 MongoDB
身份设计。matcher 允许 scalar predicate 穿透 stored array。对
scalar `1` 的直接 canonical lookup 找不到 stored `_id: [1, 2]`，
但 matcher 认为它匹配。`IdIndex.has_root_array` 检测这种 collection
状态；`_id_lookup_values` 与 `_id_lookup_is_safe_with_array_ids`
允许 whole-array lookup，却把 scalar equality 与 scalar `$in` 回退
为 `COLLSCAN`。

第二，multikey index 保存独立 leaf；没有 `$elemMatch` 时，matcher
可能让不同数组元素满足不同 operator。文档
`{"values": [1, 20]}` 会匹配
`{"values": {"$gt": 10, "$lt": 5}}`，因为两个比较由不同元素满足。
若在单个 leaf key 上交集两个条件，会错误丢掉它。因此
`SecondaryIndex.prefix_length` 对这种不安全形状返回无前缀，规划器
扫描 collection。

这些回退表达了核心规则：慢但完整的计划胜过快但不完整的计划。

## 8.6 与真实 MongoDB 对照

MongoDB 查询规划器会考虑多个候选 plan tree，可使用统计、plan cache、
trial execution、index intersection、covered query、sort satisfaction
与大量 stage。真实 `explain()` 有 verbosity mode，可报告 rejected
plan、执行时间、works、yields 与 storage metric；常规 driver 用法中
它是 cursor 操作。

MiniMongoDB 直接暴露 eager `Collection.explain(query)`，只返回一个
获胜 `IXSCAN` 或 `COLLSCAN` 与三个计数。它没有 statistics catalog、
histogram、plan cache、intersection、covered query、optimizer、timing
或 rejected-plan list。二级索引是内存 map 而非 B-tree。aggregation
中的 `$match` 也不会 pushdown 到该规划器。

完整合同见
[差异：索引与规划器](../DIFFERENCES.md#索引与规划器差异)以及
[MiniMongoDB ↔ MongoDB 映射](../mapping.md)的 `plan.choose_plan` 行。
应保留语义资格、selective access、候选过滤与工作量观测这些思想；
不能从微型 estimate 推断生产计划质量。

## 8.7 动手实验：让 winning plan 改变

运行：

```bash
UV_CACHE_DIR=/tmp/minimongodb-uv-cache uv run python labs/lab_explain.py
```

实测输出：

```text
before index: COLLSCAN
docs examined: 4
after index: IXSCAN
docs examined: 1
```

查询与答案不变，改变的只有候选来源与 matcher 工作量。再运行聚焦合同：

```bash
UV_CACHE_DIR=/tmp/minimongodb-uv-cache uv run pytest -q tests/test_planner.py
```

实测输出：

```text
......                                                                   [100%]
6 passed in 0.05s
```

该 suite 包含复合前缀、不 selective 索引、自动 `_id_` 与 multikey
正确性回退。它使用直接 API，不使用 socket。

## 8.8 练习

### 理解题 1：输掉的索引

collection 有 100 个文档，最佳可用索引产生 100 个候选 owner。哪个
stage 获胜？为什么？

??? note "参考答案"
    `COLLSCAN` 获胜。`choose_plan` 只在候选 estimate 严格小于
    `document_count` 时选索引。相等工作量不足以让本模型走额外索引
    路径。

### 理解题 2：复合前缀

索引为 `{tenant: 1, created: 1, kind: 1}`，查询为
`{tenant: "a", created: {"$gte": 10}, kind: "error"}`。可用前缀
是什么？

??? note "参考答案"
    可用前缀长度为二：先是 `tenant` 相等，再是 `created` range。
    前缀在 range predicate 后停止，所以 `kind` 不是 index bound；
    matcher 仍检查完整查询。

### 动手题 3：暴露前缀长度

在临时分支给二级 `IXSCAN` summary 增加 `prefixLength`。验收：
`tenant_1_kind_1` 对 `{tenant: "a", kind: "rare"}` 的 explain 测试
断言 `prefixLength == 2`，并有意识地更新现有 summary 测试；运行
`uv run pytest -q tests/test_planner.py`。

??? note "参考答案"
    只需扩展 `Plan.summary`：

    ```diff
     return {
         "stage": "IXSCAN",
         "indexName": self.index.name,
         "keyPattern": self.index.key_pattern,
         "indexBounds": {...},
    +    "prefixLength": self.prefix_length,
     }
    ```

    需单独决定 `_id_` summary 是否也报告 `1`，并用测试固定合同。
    本教程不应用源码改动。

## 小结

MiniMongoDB 先验证查询语法、证明索引资格，再按候选 ownership 与确定性
tie-break 排名，最终仍让 matcher 掌握语义权威。`explain` 报告候选
来源以及真实 key/document/result 计数。第 9 章从“选择来源”转向
“组合变换”：文档将流过 streaming 与 blocking aggregation stage。
