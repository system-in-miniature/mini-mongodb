# 第 7 章：二级索引与 Multikey 展开

索引不只是更快的字典查找。它是 collection 状态的第二种表示，拥有自己
的相等规则、排序规则、唯一约束与发布时间。只要其中一条规则与文档
matcher 不一致，索引就可能让正确查询返回错误答案。MiniMongoDB 把
机器结构缩小到可读范围，同时保留这些正确性边界。

## 学习目标

学完本章，你将能够：

- 规范化单字段/复合索引规格，并解释为何只允许升序；
- 追踪点路径如何穿越数组、展开为 multikey，再做 BSON 类型标记的
  canonicalization；
- 解释为什么唯一性检查前要去掉同一文档产生的重复键；
- 预测复合索引何时拥有可用的最左前缀；
- 说明索引验证、持久日志与索引发布为什么必须按这个顺序发生。

## 7.1 同一个值需要两种表示

核心实现是 `src/minimongodb/index/secondary.py` 的
`SecondaryIndex`。它维护两个字典：`_values` 保存原始 BSON 形状的
tuple 供有序比较；`_owners` 把规范化复合键映射到拥有该键的文档
标识集合。

为什么不能直接把 Python 值用作字典键？文档与数组不可 hash，而且
Python 认为 `True == 1`。MiniMongoDB 的 BSON 合同要求 Boolean 与
number 身份不同，却要求数值相等的 int/float 相等。
`src/minimongodb/bson/types.py` 的 `canonical_key` 递归加入类型 tag
并转换为可 hash 结构。`IdIndex` 与 `SecondaryIndex` 都使用它，所以
身份、唯一性与查询 bucket 共享同一个相等模型。

排序是另一项工作。`SecondaryIndex._sort_token` 用 `_CompoundSort`
包装原值；`_CompoundSort.__lt__` 逐字段调用 `bson_compare`。这样遵循
MiniMongoDB 写明的教学排序，而不是 Python 无法比较的混合类型。
把规范身份与原始排序值分开，能防止便捷的 hash 表示悄悄变成排序语义。

API 边界上的 `normalize_index_spec` 接受字段字符串、mapping 或有序
`(field, direction)` 对。它拒绝空 pattern、重复字段、空名称与除
`1` 外的所有方向。`default_index_name` 连接规范化组件，因此
`[("team", 1), ("profile.city", 1)]` 变成
`team_1_profile.city_1`。

## 7.2 从点路径到 multikey 记录

索引提取从 `SecondaryIndex._document_entries` 开始。它对每个索引字段
调用 `_field_values`，再计算各字段值列表的笛卡尔积。每个积 tuple
形成一条复合索引记录。

`_resolve_index_path` 的路径遍历有三种关键情况：

1. 字典消费下一个路径组件；
2. 列表遇到数字组件时选择明确的数组位置；
3. 列表遇到非数字组件时，把尚未消费的路径应用到每个元素并合并结果。

路径解析后，`_leaves` 递归展平数组。因此
`{"tags": ["database", "python"]}` 为 `tags` 索引贡献两个键；
`{"items": [{"sku": "A"}, {"sku": "B"}]}` 为 `items.sku` 索引
贡献 `A` 与 `B`。缺失字段贡献类 null 键 `None`，符合本项目的非
sparse 设计。

笛卡尔积对复合索引很重要。如果 `tags` 产生两个值、`regions` 产生
三个值，该文档拥有六个复合键。MiniMongoDB 有意允许多个索引字段同时
是数组；真实 MongoDB 会拒绝同一文档中多个索引字段为数组的复合
multikey index。

返回记录前，`_document_entries` 规范化每个 tuple，并用字典去重。
所以 `["database", "database"]` 会让索引成为 multikey，却只给该
文档一条 `database` 记录。没有去重时，一个文档可能在 unique
multikey index 中与自己冲突，扫描计数也会受重复数组元素而非
ownership 影响。

`SecondaryIndex.add` 会在提取过程遍历或展开数组时设置粘性的
`is_multikey` 标志，再把规范化 `_id` 加入每个 ownership bucket。
`remove` 删除 ownership 和空 bucket，`replace` 执行两者。公开的
`Collection.index_information` 报告 key pattern、unique、multikey
状态与不同 key bucket 数，而不泄露内部 map。

## 7.3 唯一性是一种前瞻验证

对 unique index，必须在冲突状态可见前失败。
`SecondaryIndex.validate_documents` 复制当前 ownership set，模拟
加入整个候选 batch。判断其他 owner 是否冲突前，它会排除候选自身的
文档身份。`validate_replace` 同样允许文档保留自己的旧键，却拒绝
另一个文档已经拥有的键。

`src/minimongodb/collection.py` 的 `Collection.create_index` 展示了
完整构建顺序：

1. 规范化规格并检查同名定义；
2. 构造尚未发布的 `SecondaryIndex`；
3. 验证全部现有文档并建立记录；
4. emit 持久的 `create_index` oplog 记录；
5. 最后才发布到 `self._indexes`。

验证或 journal append 失败时，collection 不会出现部分可见索引。
之后的 insert 会对所有二级索引验证完整候选 batch，再逐文档提交。
update 在 emit 后像前对每个索引验证候选。`Oplog.emit` 成功后，
`_replace_at` 才交换文档、更新 `_id` 并调用
`SecondaryIndex.replace`。

索引定义通过两条路径跨重启保留。它本身是 oplog 操作，所以 journal
重放会调用 `Collection._restore_index`；它也通过
`Collection._index_definitions` 写进 database checkpoint。恢复时
从 checkpoint 文档重建记录，而不是序列化内部 bucket。
`test_index_definition_survives_journal_and_checkpoint_recovery`
同时验证了两条路径。

## 7.4 前缀与候选 ownership

复合键顺序限制了可用搜索。`SecondaryIndex.prefix_length` 在第一个
缺失索引字段处停止，并在 range predicate 后停止。相等与 `$in` 可以
继续前缀；`$gt/$gte/$lt/$lte` 可以关闭前缀；不支持的 operator
不能形成可用前缀。

对索引 `{tenant: 1, kind: 1}`，查询
`{tenant: "a", kind: "rare"}` 可使用两个组件。查询
`{kind: "rare"}` 不能跳过 `tenant`，所以索引不可用。这就是生产
有序复合索引使用的最左前缀心智模型。

Multikey 正确性还带来更严格的回退。没有 `$elemMatch` 时，不同条件
可能由不同数组元素满足。交集 leaf-key bound 可能丢掉 matcher 本应
接受的文档。因此 `prefix_length` 拒绝 multikey index 上不安全的
多 operator 或 literal-array bound。第 8 章会继续跟踪这个决策如何
进入计划选择与 `explain`。

## 7.5 与真实 MongoDB 对照

MongoDB 使用生产存储引擎结构实现索引，支持升序/降序键，以及 sparse、
partial、wildcard、hashed、text、geospatial、TTL 等索引族。它跟踪
multikey path 元数据，把索引集成进并发与恢复，并拥有更丰富的数组
bound compounding 规则。

MiniMongoDB 使用内存有序 canonical map，只允许升序二级/复合索引，
支持点路径、unique constraint 与 multikey fan-out。缺失字段占据类
null 键；因为没有 sparse 选项，unique index 只允许一个 missing/null
owner。多个数组字段的复合笛卡尔积明确比 MongoDB 更宽松。索引 bucket
是 owner set，不是 B-tree page。

精确声明见
[差异：索引与规划器](../DIFFERENCES.md#索引与规划器差异)以及
[MiniMongoDB ↔ MongoDB 映射](../mapping.md)的
`index.SecondaryIndex` 行。可迁移的不变量是 canonical equality、
multikey ownership、最左前缀、前瞻唯一性检查和原子发布，而不是数据
结构或完整功能面。

## 7.6 动手实验：观察一对多 ownership

运行：

```bash
UV_CACHE_DIR=/tmp/minimongodb-uv-cache uv run python labs/lab_multikey_index.py
```

实测输出：

```text
one document can contribute several multikey index entries
index keys: 4 multikey: True
matched document ids: [1, 2]
```

三个文档共有五个数组元素，却只有四个不同 key bucket：`database`
由文档 1 与 2 共享。因此 “entries” 指不同 canonical index key，
不是文档数，也不是原始数组元素数。

运行聚焦测试：

```bash
UV_CACHE_DIR=/tmp/minimongodb-uv-cache uv run pytest -q tests/test_indexes.py
```

实测输出：

```text
.........                                                                [100%]
9 passed in 0.16s
```

这些直接 API 实验不使用 socket，并已在本仓库实跑。

## 7.7 练习

### 理解题 1：重复数组元素

对 `tags` 的非 unique index，
`{"_id": 1, "tags": ["db", "db", "python"]}` 贡献几个 owned key？
索引是否为 multikey？

??? note "参考答案"
    它贡献 `db` 与 `python` 两个键，因为
    `SecondaryIndex._document_entries` 会按文档去重 canonical
    compound key。`is_multikey` 仍为 true，因为提取展开了数组；
    multikey 描述路径形状，而不是重复数。

### 理解题 2：缺失值与 unique index

为什么在 `email` unique index 下只能存在一个缺少 `email` 字段的
文档？

??? note "参考答案"
    `_field_values` 把缺失索引字段映射为 `[None]`。没有 sparse index
    选项时，missing 与显式 null 占同一个 canonical bucket，而
    uniqueness 只允许一个文档 owner。

### 动手题 3：报告 owned key 数

在临时分支为 `SecondaryIndex` 增加只读教学方法
`owned_keys(document)`，返回文档将拥有的去重键数。验收：测试一个
有重复值的二值数组与一个 2×3 双字段复合积，期望 `2` 与 `6`；运行
`uv run pytest -q tests/test_indexes.py`。

??? note "参考答案"
    实现可委托已有方法，且不泄露私有 map：

    ```diff
    +def owned_keys(self, document: dict[str, Any]) -> int:
    +    return len(self.document_keys(document))
    ```

    可直接构造 `SecondaryIndex` 测试，或有意识地增加 collection 教学
    API。不要数原始 leaf。本教程保持 `src/` 不变。

## 小结

二级索引是与文档状态同步的 canonical view。MiniMongoDB 分离相等键与
排序值，把点路径数组展开为去重 ownership bucket，前瞻验证唯一性，并
只在持久接收后发布定义与变更。第 8 章把这些 bucket 用作候选估算，
继续追问：一个可用索引究竟何时更便宜、且语义安全？
