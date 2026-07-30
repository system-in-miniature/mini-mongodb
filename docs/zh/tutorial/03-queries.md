# 第 3 章：查询语义

[English](../../tutorial/03-queries.md)

当一条路径可能表示标量、数组、嵌入文档，或穿过文档数组得到的多个值时，文档查询会变得微妙。MiniMongoDB 把这些规则集中在一个小 matcher 中。planner 可以选择候选，但语义权威始终是 `src/minimongodb/query/matcher.py::matches`。

## 学习目标

学完本章，你将能够：

- 从 `Collection.find` 经 planning 追踪到 `matches`；
- 区分标量数组匹配、整体数组相等、整体文档相等和点路径展开；
- 解释已支持字段算子与逻辑算子的行为；
- 推理 missing、`$ne`、`$exists`、`$not`；
- 指出哪些查询行为有意不兼容 MongoDB。

## Planning 不定义真值

`src/minimongodb/collection.py::Collection._run_query` 把 `None` 规范化为空查询，校验语法，再调用 `src/minimongodb/plan/__init__.py::choose_plan`。计划要么不给 candidate id（扫描 `_documents`），要么提供索引产生的 id 集合。两种情况下，最后都用同一个 `matches(document, normalized)` 过滤。

这一分工至关重要。索引只存文档投影，对复杂语义可能产生假阳性；只有在绝不漏掉真匹配时，它才能安全缩小工作量。matcher 是 residual predicate，也是最终裁判。第 8 章会研究 planner；现在只需把它看成稳定语义核心之外的优化。

即使索引提供无序 ownership set，`Collection._run_query` 仍按存储插入顺序遍历。因此增加索引可以改变 `docsExamined`，不能改变匹配语义或公开结果顺序。

## 从点路径到候选值

对查询中的每个普通字段，`src/minimongodb/query/matcher.py::matches` 调用 `resolve_path`。字典消费一个字段段；数字段选择一个列表位置；非数字段作用于列表时会展开：对每个数组元素应用同一剩余路径，并连接所选值。

给定：

```python
{"items": [{"sku": "A", "qty": 1}, {"sku": "B", "qty": 4}]}
```

路径 `items.sku` 解析出 `"A"`、`"B"`。缺失路径解析为空列表，而不是 `[None]`，所以 presence 就是 `bool(values)`，这为 `$exists` 提供语义。

解析后，`_field_matches` 判断条件是 operator document 还是字面量。包含美元前缀键的字典是 operator document；混合 operator 与普通键会被拒绝。普通字典是嵌入文档字面值，使用精确 BSON 形状相等。

## 数组规则：仅对标量形状操作数展开

`src/minimongodb/query/matcher.py::_array_candidates` 包含核心规则：若存储所选值是 list，而预期查询操作数既非 list 也非 dict，就递归产生标量叶；否则把存储值作为整体产生。

由此得到四种必须记住的行为：

1. 存储 `["database", "python"]` 用标量 `"python"` 查询，会自动匹配元素。
2. 同一数组用字面量 `["database", "python"]` 查询，会比较含顺序的完整数组。
3. 存储 `{"city": "London", "role": "engineer"}` 用字面量 `{"city": "London"}` 查询会失败，因为文档按整体比较。
4. 查询 `profile.city` 会先选择 `"London"`，无关 `role` 不再参与。

在这个教学子集中，嵌套数组也会为标量操作数递归暴露叶值。这条紧凑规则比完整 MongoDB matcher 更宽松也更不完整，但清楚说明“数组相等”不是一个单一操作：操作数形状决定存储数组是待遍历容器，还是待比较值。

范围比较复用这种展开。`src/minimongodb/query/matcher.py::_compare` 对每个候选应用 `bson_compare`，任一候选满足 `$gt/$gte/$lt/$lte` 即接受；类型错误会成为不匹配，而不是泄露 Python 异常。

## 字段算子

`_operator_matches` 实现以下集合：

- `$eq` 使用上述相等行为；
- `$gt/$gte/$lt/$lte` 使用项目比较序；
- `$in` 在任一已解析值等于任一选项时接受；
- `$ne` 在没有已解析值等于操作数时成功；
- `$exists` 比较请求布尔值与 `bool(values)`；
- 字段级 `$not` 否定一个 operator document。

presence 检查的位置很重要。`$ne` 位于通用“缺失则 false”分支之前，所以缺失字段匹配 `{"field": {"$ne": value}}`；`$exists: false` 也匹配缺失。普通相等、范围和 `$in` 则要求值存在。

operator document 内的项目以 `all` 组合。对标量字段，`{"age": {"$gte": 18, "$lt": 65}}` 是常见区间；对数组路径，多个算子可由不同元素分别满足，因为 MiniMongoDB 没有 `$elemMatch`。`{"scores": [2, 20]}` 可以同时满足 `$gt: 10` 与 `$lt: 5`。完整 MongoDB 在不使用 `$elemMatch` 时有相似概念，但本项目的递归展开与 planner 防护仍是自己的子集。

## 逻辑算子

在顶层，`matches` 递归处理 `$and`、`$or` 数组。普通字段条件已经由外围循环隐式 AND；当同一字段需出现在多个表达式对象，或程序化组装查询时，显式 `$and` 有用。

MiniMongoDB 还接受项目专属的顶层 `$not` 查询文档，递归匹配子查询后取反。真实 MongoDB 不支持顶层 `$not`，而支持 `$nor` 和字段级 `$not`；使用本地扩展的查询有意不可移植。

未知美元前缀键会抛出 `InvalidQueryError`。即使集合为空也会校验，因为 `_run_query` 在 planning 前调用 `matches({}, query)`。坏查询不能仅因当前无数据或索引给出零候选就悄悄变合法。

## 与真实 MongoDB 对照

标量匹配存储数组元素、嵌入文档精确相等和点路径穿过文档数组，都是有用的 MongoDB 形状课程。但 MiniMongoDB 只实现 `$eq/$gt/$gte/$lt/$lte/$ne/$in/$exists/$and/$or/$not`，没有 regex、collation、`$elemMatch`、`$all`、`$size`、地理谓词、表达式查询或完整 MQL。

真实范围谓词通常做 type bracketing；本项目暴露小型全局跨类型顺序。真实 `{field: null}` 也匹配缺失；这里仅匹配显式 `None`。顶层 `$not` 扩展与 MongoDB 语法相反。`find` 返回 eager list，没有 cursor、projection、sort、skip、limit、hint 或 read concern。

详见[查询差异](../DIFFERENCES.md#查询差异)。[映射表](../mapping.md#minimongodb--mongodb-映射)分别标注标量-数组相等、嵌入文档相等、范围比较和顶层 `$not`，不能把不同 parity 等级压成一句“查询兼容 MongoDB”。

## 动手实验：形状的三种含义

运行仓内 lab：

```bash
UV_CACHE_DIR=/tmp/minimongodb-uv-cache uv run python labs/lab_array_matching.py
```

实测输出：

```text
scalar array match: ['Ada']
  A scalar query inspects each stored array element automatically.
literal nested document: []
  A document literal means exact whole-document equality; extra keys matter.
dotted path match: ['Ada']
  A dotted path selects one nested field, so unrelated keys do not matter.
```

第一项来自 `_array_candidates`；第二项来自完整嵌入文档上的精确 `bson_equal`；第三项来自 `resolve_path` 先选出标量。命令只使用进程内 API，不是 socket 或官方驱动兼容测试。

## 练习

### 1. 理解题：整体数组还是元素？

对 `{"tags": ["database", "python"]}`，预测查询 `{"tags": "python"}`、`{"tags": ["database", "python"]}`、`{"tags": ["python", "database"]}` 的结果，并说明哪个源码函数控制差异。

??? note "参考答案"

    前两个匹配，反序数组字面量不匹配。标量 `"python"` 使 `_array_candidates` 暴露元素；list 操作数让存储 list 保持整体，`bson_equal` 保留数组顺序。

### 2. 理解题：missing、null 与否定谓词

计算空文档对 `{"x": None}`、`{"x": {"$exists": False}}`、`{"x": {"$ne": 3}}` 的结果。

??? note "参考答案"

    null 字面量为 false，因为没有解析值；`$exists: false` 为 true，因为不存在；`$ne: 3` 为 true，因为没有解析值等于 3。这不同于真实 MongoDB 的 null-or-missing 行为。

### 3. 动手题：以补丁提案增加 `$nor`

起草源码和测试 diff，但不修改 `src/`。验收：非 list 操作数被拒绝；仅当所有子查询均不匹配时返回 true；包含正向、反向和 malformed 测试。

??? note "参考答案"

    在 `matches` 的 `$and/$or` 附近加入：

    ```diff
    + elif key == "$nor":
    +     if not isinstance(condition, list):
    +         raise InvalidQueryError("$nor requires an array")
    +     if any(matches(document, child) for child in condition):
    +         return False
    ```

    测试应证明 Ada/20 对 `{"$nor": [{"age": 10}, {"name": "Grace"}]}` 成功、任一子项匹配时失败、document 操作数抛错。验收是在一次性 worktree 应用提案后目标测试全绿，再还原；当前仓不落源码改动。

### 4. 动手题：暴露跨元素匹配

不改源码，插入 `{"_id": 1, "scores": [2, 20]}` 并查询 `{"scores": {"$gt": 10, "$lt": 5}}`。验收：打印匹配 `_id`，并用一句话解释 `$elemMatch` 会表达何种不同约束。

??? note "参考答案"

    MiniMongoDB 返回文档 1：20 满足 `$gt`，2 满足 `$lt`。`$elemMatch` 会要求同一元素满足二者，而这里没有任何元素可以；本项目未实现 `$elemMatch`。

## 小结

查询语义只有一个所有者：`matches`。点路径解析可产生多个候选；标量操作数可展开存储数组，而数组与文档字面量保持精确整体值。随后算子组合 presence、相等或比较，逻辑算子递归查询。第 4 章会复用路径遍历与匹配，但问题变为：如何原子构造新文档，同时保持标识不变。
