# 第 4 章：更新算子

[English](../../tutorial/04-updates.md)

查询负责选择文档；更新必须转换它，同时不能留下半应用状态、泄露调用者对象、改变 `_id`，也不能在持久化之前发布索引。MiniMongoDB 先构造候选副本，全部检查成功后才交换到集合存储，使这条顺序清晰可见。

## 学习目标

学完本章，你将能够：

- 区分算子更新与替换更新；
- 从源码追踪 `$set/$unset/$inc/$push/$pull`；
- 解释 copy-compute-validate-publish 单文档原子性；
- 解释不可变 `_id` 与 matched/modified 计数；
- 指出 upsert、array filters 等未实现的生产能力。

## 两种更新语言，两个公开方法

`src/minimongodb/collection.py::Collection.update_one`、`update_many` 只接受 operator document。`Collection._update` 拒绝空更新、普通 replacement，以及顶层 operator 与普通键的任何混合，并要求替换语法使用 `replace_one`。

下面是算子更新：

```python
{"$set": {"profile.city": "London"}, "$inc": {"visits": 1}}
```

下面是替换：

```python
{"profile": {"city": "London"}, "visits": 1}
```

前者修改指定路径并保留其他字段；后者替换整个文档，只在省略时保留旧 `_id`。`replace_one` 拒绝美元前缀顶层键，避免两种语言暗中交叉。

对每个已存文档，`Collection._update` 调用 `src/minimongodb/query/matcher.py::matches`。`update_one` 在首个匹配后停止，`update_many` 继续。`matched_count` 统计满足查询的文档；`modified_count` 统计候选与原件并非 BSON-equal 的文档。把字段设为当前值会匹配但不修改，也不发 oplog 或重建索引。

## 在私有副本上计算

`src/minimongodb/update/operators.py::apply_operator_update` 从 `clone_document(original)` 开始。每个算子都修改该私有副本；多个操作中的第二个失败时，存储原件仍未触碰。全部操作完成后，函数再次 clone 候选。第二道边界既校验新引入的嵌套值，也切断来自用户更新文档的可变对象别名。

成功更新的流程是：

```text
匹配存储原件
  -> clone 原件
  -> 应用每个路径操作
  -> 校验并再次 clone 候选
  -> 比较候选与原件
  -> 校验所有受影响 unique 二级索引
  -> 发出持久/逻辑变更
  -> 替换存储文档与索引项
```

`Collection._replace_at` 执行最终发布：交换列表项、替换 `_id` map 值，并让每个二级索引用新键替换旧键。若来自持久化 `Database`，`Oplog.emit` 会先调用 journal listener，所以 journal 失败发生在发布前。第 5 章将沿边界进入存储。

该模型在单个 Python 进程中对一个文档原子：失败算子不会暴露部分候选。它不是并发客户端间的事务隔离，多文档更新也不是 all-or-nothing。

## 五个算子

`apply_operator_update` 只允许 `SUPPORTED_OPERATORS` 中的名称；`_mapping_operand` 要求每个 operand 都是 path 到 value 的文档。

### `$set` 与 `$unset`

`$set` 委托给 `src/minimongodb/bson/path.py::set_path`。可创建缺失字典父级，但不会创造或扩展数组；数字数组位置必须已存在。

`$unset` 调用 `unset_path`。删除文档字段会移除键；unset 已存在列表位置则写 `None`，避免后续位置移动；缺失路径是 no-op。

### `$inc`

`$inc` 用 `get_path` 取得当前值。增量必须是实数但不能是 bool；目标缺失时，增量成为初值；目标存在时也必须是非 bool 数字，随后存入 `current + amount`。

拒绝 bool 再次体现数据库类型语义覆盖 Python 的 `bool`-is-`int` 继承。数值检查失败会抛 `InvalidUpdateError`，私有候选随即丢弃。

### `$push`

`$push` 向现有 list 追加一个值；字段缺失时创建单元素 list；已存在的非 list 目标会报错。微缩实现不支持 `$each/$slice/$sort/$position` 等 MongoDB modifier。

### `$pull`

`$pull` 要求已存在目标是 list。它用普通 matcher 匹配合成文档来删除元素：

```python
matches({"value": item}, {"value": value})
```

所以 `$pull: {"scores": {"$gt": 5}}` 继承查询子集的比较语义。目标缺失为 no-op，非 list 则失败。

## `_id` 不可变

每条 operator path 都先经过 `src/minimongodb/update/operators.py::_guards_id`，拒绝 `_id` 和以 `_id.` 开头的路径。删除、递增或局部修改标识都会破坏集合唯一 identity map，以及 oplog replay 使用的 key。

`replacement_document` 用另一方式维护同一不变量：clone replacement，读取旧 identity，若用户提供不相等 `_id` 则拒绝；若省略则插入旧值。在教学表示中该字段可能出现在较后的插入顺序，因此实验替换文档先打印 `status`、后打印 `_id`。

候选构造后，`Collection._update` 在 emit 或 publish 前让每个二级索引执行 `validate_replace`。因此 unique 索引冲突会让文档、oplog 和所有索引保持原样。

## 从动作到后像

用户更新表达动作：递增、追加或删除。直接重放动作两次可能改变两次状态。emit 更新前，`src/minimongodb/collection.py::Collection._post_image_update` 从最终候选读取每个请求路径，并改写为 `$set` 或 `$unset`。从 2 加 3 进入 oplog 时就是 `{"$set": {"count": 5}}`。

第 6 章会完整研究该幂等机制。此处先注意职责分离：`apply_operator_update` 实现用户请求的转换，`_post_image_update` 实现可安全重复的日志表示。已存文档和 oplog 不需要用相同语法表示同一已接受变更。

## 与真实 MongoDB 对照

真实 MongoDB 也区分 replacement 与 operator update，保护不可变 `_id`，并提供单文档原子性。本地 `$set/$unset/$inc/$push/$pull` 有意模拟一个小而有用的子集，包括 `$unset` 保持数组位置。

MiniMongoDB 没有 upsert、位置 `$`、`$[]`、filtered positional operator、array filters、update pipeline、collation、write concern、session、transaction、retryable write 或 find-and-modify；`$push` 不含 modifier；`$pull` 复用本地 matcher，因此继承不可移植的全局类型序和本地扩展。

`update_many` 等批量操作逐文档提交。若第 N 个文档持久 append 失败，之前项目保持可见且持久，第 N 个和后续项目不发布。这是 committed-prefix 合同，不是多文档事务。

参见[更新与 CRUD 差异](../DIFFERENCES.md#更新与-crud-差异)，以及[映射表](../mapping.md#minimongodb--mongodb-映射)中的 `update.operators`、`collection.Collection` 行。

## 动手实验：算子与替换

运行：

```bash
UV_CACHE_DIR=/tmp/minimongodb-uv-cache uv run python - <<'PY'
from minimongodb import Collection
items = Collection("items")
items.insert_one({"_id": 1, "stats": {"count": 2}, "tags": ["db", "old"]})
result = items.update_one(
    {"_id": 1},
    {"$inc": {"stats.count": 3}, "$push": {"tags": "python"}, "$pull": {"tags": "old"}},
)
print("counts:", result.matched_count, result.modified_count)
print("updated:", items.find_one())
replacement = items.replace_one({"_id": 1}, {"status": "archived"})
print("replacement counts:", replacement.matched_count, replacement.modified_count)
print("replaced:", items.find_one())
PY
```

实测输出：

```text
counts: 1 1
updated: {'_id': 1, 'stats': {'count': 5}, 'tags': ['db', 'python']}
replacement counts: 1 1
replaced: {'status': 'archived', '_id': 1}
```

算子更新保留无关结构并修改指定路径；替换删除旧结构，只保留不可变 identity。该 direct API 实验不验证 socket 或驱动。

## 练习

### 1. 理解题：匹配但未修改

两个文档均为 `x=1`，随后执行 `update_many({"x": 1}, {"$set": {"x": 1}}`，计数应为何？

??? note "参考答案"

    `matched_count` 为 2，`modified_count` 为 0。两个文档都匹配，但候选均与原件 BSON-equal，无需 oplog 或索引替换。

### 2. 理解题：失败原子性

一次更新先含合法 `$set`，随后对字符串做 `$inc`。为什么第一项合法变更也不可见？

??? note "参考答案"

    所有算子修改私有 clone，只有全部操作和校验成功后才返回。错误 `$inc` 在 `Collection._update` emit 或 `_replace_at` 前抛出，所以存储原件不变。

### 3. 动手题：提案 `$rename`

起草但不应用 `$rename` diff。验收：source/destination 都防护 `_id`；拒绝重叠或非法路径；缺失 source 为 no-op；保持 copy-first 原子性；提出嵌套路径和失败回滚测试。

??? note "参考答案"

    完整设计把 `$rename` 加入 `SUPPORTED_OPERATORS`，要求 destination 为字符串，对两端调用 `_guards_id`，用 `get_path` 读取 source，存在时先 `set_path(destination, value)` 再在私有候选上 `unset_path(source)`。必须定义并拒绝祖先/后代重叠。测试覆盖嵌套成功、缺失、不可变 identity、非法 destination、重叠，以及多算子失败后存储不变。

### 4. 动手题：验证调用者值隔离

把调用者拥有的嵌套字典 `$set` 到字段，`update_one` 后再修改该字典，然后读取。验收：存储嵌套内容必须保持修改前值。

??? note "参考答案"

    令 `value = {"items": [1]}`，经 `$set` 写入，再向 `value["items"]` 追加 2。存储结果仍应为 `{"items": [1]}`，因为 `apply_operator_update` 最后执行校验性 clone。

## 小结

MiniMongoDB 清楚分开算子更新与替换：在私有副本计算，校验值和索引，发出已接受变更，最后替换存储状态。五个算子共享点路径机制；不可变 `_id` 保护 identity 与 replay。第 5 章会给“已接受”加入崩溃边界：集合属于 `Database` 时，变更必须先到达 fsync 的 journal 帧，内存与索引才能发布。
