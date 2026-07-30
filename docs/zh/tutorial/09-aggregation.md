# 第 9 章：作为文档流水线的聚合

查询回答哪些文档匹配；aggregation pipeline 回答更宽的问题：一条文档流
应如何过滤、重塑、合并、排序与截断？MiniMongoDB 把 `$match`、
`$project`、`$group`、`$sort`、`$limit` 五个 stage 实现为小型可组合
operator。关键课程不在 stage 数量，而在什么 stage 可以流式处理、什么
语义迫使它物化全部输入。

## 学习目标

学完本章，你将能够：

- 从 `Collection.aggregate` 追踪到 `execute_pipeline` 与 stage dispatch；
- 把 `$match/$project/$limit` 归为 streaming stage，把
  `$group/$sort` 归为 blocking stage；
- 计算字段引用与嵌套 expression shape；
- 解释 group identity、accumulator 初始化与 missing-value 行为；
- 指出哪些 MongoDB aggregation 能力与优化被有意省略。

## 9.1 Pipeline 是分阶段 iterable 组合

`src/minimongodb/collection.py` 的 `Collection.aggregate` 把 collection
文档列表传给 `src/minimongodb/aggregate/__init__.py` 的
`execute_pipeline`。后者先检查 pipeline 是 list，再创建一个逐个 clone
源文档的 generator。因此 aggregation 不会向调用者泄露内部可变文档，
也不会改变 collection 状态。

每个 stage 必须是恰含一个 operator 的字典。dispatcher 验证 stage
顶层形状，并把 `stream` 替换为下一个 iterable：

```python
for stage in pipeline:
    operator, specification = next(iter(stage.items()))
    if operator == "$match":
        stream = _match(stream, specification)
    elif operator == "$project":
        stream = _project(stream, specification)
    ...
return list(stream)
```

公开结果最终是 eager list，但中间值通常是 iterable。这让前置 `$match`
能在后续工作前丢弃文档，也让 `$limit` 停止 pull。stage 顺序可观察：
若先 project 掉一个字段，后续 match 看到的文档形状就已改变。

组合还把责任局部化：dispatcher 拥有 stage syntax，每个 helper 拥有
一种 transformation，末尾 `list(stream)` 拥有公开 materialization。
helper 不必知道输入来自 collection、matcher 还是另一个 projection。
这正是 iterator-based operator engine 易于教学的接口优势。

非法结构会明确抛出 `InvalidPipelineError`：非 list pipeline、包含两个
operator 的 stage、未知 stage 名和非法规格都不会被静默忽略。

## 9.2 Streaming stage

`_match` 是 generator。它每次 pull 一个文档，调用现有
`query.matches`，只 yield 接受的文档。这个复用很重要：数组 fan-out、
嵌入文档精确匹配、点路径与支持的 query operator 不会获得第二套
aggregation 专属解释。然而 `_match` 直接接收当前 pipeline iterable，
不调用 `Collection._run_query`，所以没有 index planning 或 pushdown。

`_project` 也是 generator。它先把表达式为 `0`/`False` 的字段归为
exclusion，其余归为 inclusion 或 computed field。除 `_id` 外的排除
不能与 inclusion/computed expression 混用。在 inclusion mode 中，
默认保留 `_id`，直接 `1`/`True` 字段通过 `get_path` 读取，其余表达式
交给 `_evaluate`。在 exclusion mode 中，它 clone 完整文档，再对每个
排除字段调用 `unset_path`。

`_limit` 验证非负整数，并 yield 到 enumeration position 到达 limit。
虽然 Python 的 `bool` 是 `int` 子类，这里会显式拒绝 Boolean。到达
limit 时，它 break 且不再 pull 剩余 upstream iterable。把 `$limit`
放在 blocking stage 前可限制该 stage 输入，但也会改变 pipeline 语义。

这些 stage 使用 Python generator，因此只持有当前文档和少量局部状态。
“Streaming” 不代表网络流或 async cursor；它描述一次同步调用内部的
增量消费。

## 9.3 Expression 求值

`_evaluate` 支持一门紧凑 expression language：

- 以 `$` 开头的字符串是点路径字段引用；
- 特殊字符串 `$` 引用完整文档；
- 字典与列表会递归计算为嵌套形状；
- 其他值都是 deep-copy 的常量。

缺失字段引用返回 `bson.path` 的 `MISSING` sentinel。Projection 会省略
缺失的直接字段；嵌套 list 中 missing 变为 `None`；嵌套 document 中
对应 child key 被省略。这样内部 sentinel 不会泄露成返回的 BSON 形状
值。

该语言足以表达 `{"name": "$item.name"}` projection 与 `"$region"`
group key，却没有实现 MongoDB 的算术、条件、日期、字符串、数组或变量
expression 家族。

## 9.4 为什么 group 会阻塞

`_group` 看见第一个成员时不能 yield 最终 group：之后的文档可能改变
sum、average、minimum、maximum 或 pushed list。它因此把完整输入消费
进以 `canonical_key(group_value)` 为键的 `groups` 字典。Canonical
key 让结构化 group identity 可 hash，同时保留 MiniMongoDB BSON
equality。

缺失 group key 变成 `None`。新 group 把 `$push` 初始化为空 list，
把 `$min/$max` 初始化为私有 `_UNSET` sentinel，把数值 accumulator
初始化为 `None`。sentinel 很重要，因为 BSON null 是真正可比较的值，
不能表示“尚无观察值”。

Accumulator 行为是显式的：

- `$sum` 加数值，非数值或 missing 视为零；
- `$avg` 单独跟踪 `(total, count)`，忽略非数值；
- `$min/$max` 用 `bson_compare` 比较存在的值；
- `$push` 追加计算值，并把 missing 转为 `None`。

`_numeric` 会拒绝 Boolean，尽管它继承自 Python 数值类型。消费完成后，
`_group` finalize average、empty sum 与从未见值的 min/max，再返回
`groups.values()`。

`_sort` 是另一个 blocking stage。它对完整 iterable 调用 `sorted`，
比较器读取点路径，并把混合类型排序交给 `bson_compare`。缺失 sort
字段变为 `None`。多个 sort 字段按 specification 顺序检查，每个方向
为 `1` 或 `-1`。

所以内存边界在源码中清晰可见：`_match`、`_project`、`_limit` 含
`yield`；`_group` 拥有覆盖所有 group 的字典；`_sort` 调用 `sorted`。

## 9.5 与真实 MongoDB 对照

MongoDB aggregation framework 拥有庞大 expression language，以及
`$unwind`、`$lookup`、`$facet`、`$setWindowFields`、`$merge`、`$out`
等 stage。优化器可重排/合并 stage，把可用 `$match` 推向索引，在 shard
间拆 pipeline，并在配置与限制允许时把部分 blocking 工作 spill to
disk。

MiniMongoDB 只实现 `$match/$project/$group/$sort/$limit`；`$group`
支持 `_id` 加 `$sum/$avg/$min/$max/$push`。它在单进程内处理 clone 的
稳定输入序列，没有 optimizer、index pushdown、spill、parallelism、
distributed merge、lookup、unwind、window function 或 output stage。
`$group/$sort` 的内存可随全部输入增长。

见
[差异：聚合](../DIFFERENCES.md#聚合差异)以及
[MiniMongoDB ↔ MongoDB 映射](../mapping.md)的
`aggregate.execute_pipeline` 行。可迁移模型是有序 operator 组合、
显式 expression evaluation 和 streaming/blocking ownership，而不是
生产可扩展性。

## 9.6 动手实验：过滤、分组、重塑

在仓库根目录运行以下完整命令：

```bash
UV_CACHE_DIR=/tmp/minimongodb-uv-cache uv run python - <<'PY'
import json
from minimongodb import Collection
sales = Collection("sales")
sales.insert_many([
    {"_id": 1, "region": "west", "amount": 3},
    {"_id": 2, "region": "east", "amount": 9},
    {"_id": 3, "region": "west", "amount": 7},
])
result = sales.aggregate([
    {"$match": {"region": "west"}},
    {"$group": {"_id": "$region", "total": {"$sum": "$amount"}, "avg": {"$avg": "$amount"}}},
    {"$project": {"_id": 0, "region": "$_id", "total": 1, "avg": 1}},
])
print(json.dumps(result, sort_keys=True))
PY
```

实测输出：

```text
[{"avg": 5.0, "region": "west", "total": 10}]
```

`$match` 把两个 west 文档流式传给 blocking `$group`，`$project` 再
重塑完成的一个 group。`sort_keys=True` 只规范化打印 JSON 的 key
顺序，使实测输出可重复；key 顺序不参与 total 计算。

运行聚焦合同：

```bash
UV_CACHE_DIR=/tmp/minimongodb-uv-cache uv run pytest -q tests/test_aggregate.py
```

实测输出：

```text
........                                                                 [100%]
8 passed in 0.03s
```

两个命令都只使用直接 API，不涉及 socket。

## 9.7 练习

### 理解题 1：移动 limit

`[$sort, $limit: 10]` 与 `[$limit: 10, $sort]` 等价吗？

??? note "参考答案"
    不等价。先 sort 后 limit 返回全局有序结果的前十个；先 limit 后
    sort 只消费上游前十个并对它们排序。后者限制 sort 内存，却改变
    语义。

### 理解题 2：null 与无值

为什么 `$min` 用 `_UNSET` 而不是 `None` 初始化？

??? note "参考答案"
    `None` 是 BSON null，并参与 MiniMongoDB 比较序。用它表示“尚未
    初始化”会让真实 null observation 与无 observation 无法区分。
    `_UNSET` 分开了两种状态。

### 动手题 3：增加 `$count`

在临时分支增加 blocking `$count` stage，其字符串 specification 指定
输出字段名，输出如 `{"matched": 3}`。验收：测试正常、空输入与非法
名称，再运行 `uv run pytest -q tests/test_aggregate.py`。

??? note "参考答案"
    紧凑设计是在 dispatcher 加验证与 helper：

    ```diff
    +elif operator == "$count":
    +    stream = _count(stream, specification)

    +def _count(documents, field):
    +    if not isinstance(field, str) or not field or field.startswith("$"):
    +        raise InvalidPipelineError("$count requires an output field name")
    +    count = sum(1 for _ in documents)
    +    return [] if count == 0 else [{field: count}]
    ```

    把练习当作 compatibility 工作前，应对照 MongoDB 确认空输入行为。
    本教程不修改 `src/`。

## 小结

MiniMongoDB 把 aggregation 组合成 iterable：matching、projection 与
limit 可增量消费，grouping 与 sorting 必须先拥有全部相关输入才能返回
最终答案。Canonical BSON equality 与 comparison 在查询、索引、聚合间
继续共享。第 10 章将用关系 schema、join、plan、index 与 transaction
boundary 对照这些文档机制，为全书收束。
