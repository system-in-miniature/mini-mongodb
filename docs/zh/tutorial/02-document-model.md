# 第 2 章：文档模型

[English](../../tutorial/02-document-model.md)

所有高层操作都依赖三个准确答案：哪些值合法、何时两个值相等、字段路径如何选择嵌套值。MiniMongoDB 把答案集中在 `src/minimongodb/bson/`。本章先建立值模型，再让后续查询和更新以不同方式使用它。

## 学习目标

学完本章，你将能够：

- 列出 MiniMongoDB 支持的 BSON 形状类型标签与比较序；
- 解释 `True`、`1`、文档和数组为何需要带类型相等性；
- 区分精确值相等与点路径选择；
- 追踪 `get_path`、`set_path` 和查询专用 `resolve_path`；
- 指出 MiniMongoDB 与真实 BSON 的有意差异。

## 值具有显式标签

`src/minimongodb/bson/types.py::type_tag` 接受七类值：`null`、`number`、`string`、`document`、`array`、`bool`、`objectId`。Python 值提供表示——`dict` 表示文档，`list` 表示数组——但数据库不会简单继承所有 Python 行为。集合、元组、字节、日期时间、非字符串文档键和任意对象都会被拒绝。

`type_tag` 的检查顺序很重要。Python 的 `bool` 是 `int` 子类；若先检查数字，`True` 会被标成 number。MiniMongoDB 先检查 `bool` 并赋予独立标签。这个区别会传播到相等性、标识索引、持久化和排序。

`src/minimongodb/bson/types.py::clone_document` 在 `deepcopy` 前调用递归 `_validate_tree`，因此校验不限于根节点：藏在三层数组里的 set 仍会在入库前被拒绝。受支持的对象图是值形状的，深复制清楚地表示了教学中的所有权转移。

MiniMongoDB 的 `ObjectId` 是冻结值，包含一个可装入 96 位的非负整数。`ObjectId.__str__` 渲染 24 位十六进制，所以外形熟悉；`CounterObjectIdGenerator.__call__` 产生单调值，并可注入以得到确定性测试。外形不等于来源：真实 MongoDB ObjectId 包含时间戳、随机/进程和计数器材料，本实现刻意没有。

## 精确相等是 BSON 形状的

`src/minimongodb/bson/types.py::bson_equal` 先比较类型标签。因此即便 Python 认为 `True == 1`，这里二者也不同。int 和 float 共享 `number` 标签，按数值比较，并对 NaN 作显式处理。

文档按插入顺序比较。函数先检查有序键列表，再递归比较对应值：

```python
if isinstance(left, dict):
    return list(left.keys()) == list(right.keys()) and all(
        bson_equal(left[key], right[key]) for key in left
    )
```

所以 `{"a": 1, "b": 2}` 不精确等于 `{"b": 2, "a": 1}`。数组逐元素比较，也对顺序敏感。当查询操作数本身是文档或数组时，这种精确相等至关重要：文档字面量表示“等于完整嵌入值”，而不是“包含这些字段”。

哈希表需要可哈希键，但 BSON 形状值可以包含字典和列表。`src/minimongodb/bson/types.py::canonical_key` 递归把值转换为以类型标签开头的元组。数字经过特别规范化，使普通相等的 int/float 共享标识、NaN 收敛，同时避免大整数被不精确 float 意外折叠。文档在 canonical 形式中保留字段顺序，数组保留元素顺序。

`src/minimongodb/index/id_index.py::IdIndex` 使用该键保证唯一性并查找。这就是 `_id=True` 与 `_id=1` 可以共存、而 `_id=1` 通常和 `_id=1.0` 冲突的原因。canonicalization 是 `bson_equal` 的索引表示，不是新的公开相等规则。

## 有意缩小的比较序

范围谓词和聚合排序不仅需要相等，还需要顺序。`src/minimongodb/bson/types.py::bson_compare` 先比较 `_TYPE_ORDER` 中的位置：

```text
null < number < string < document < array < bool < objectId
```

同标签值递归比较。文档比较键值序列，数组按字典序比较元素，数字比较显式处理 NaN，以保持确定性。

这个全局顺序是教学选择，不是 MongoDB 对等实现。真实 BSON 支持更多类型，并有自己的 BSON 比较序。更重要的是，MongoDB 比较查询通常使用 type bracketing：数值范围通常比较数值字段，而不是沿全局顺序跨越字符串和文档。MiniMongoDB 直接暴露其全局顺序；依赖这里跨类型范围匹配的代码不是可移植 MQL。

## 点路径：一种记法，两类读语义

CRUD 更新与聚合表达式使用 `src/minimongodb/bson/path.py::get_path`。它拆分非空点路径，遍历字典键；当前容器为列表时，接受数字段。缺少键或下标会返回哨兵 `MISSING`，它不同于已存 `None`。

这一区分让更新知道字段是“不存在”还是“显式 null”，也让聚合投影省略缺失字段而保留 null 字段。私有哨兵比拿普通用户值表示“未找到”更安全。

`set_path` 穿过现有容器，并可创建缺失的字典父级；它不会猜测如何创建或扩展数组。当前容器是列表时，路径段必须是数字，位置必须已存在。`unset_path` 删除字典键；若目标是数组位置，则写入 `None`，避免后续位置移动。

查询匹配需要不同的读操作：`src/minimongodb/query/matcher.py::resolve_path`。当非数字字段作用于数组时，它会对每个元素递归应用同一剩余路径。对于：

```python
{"items": [{"sku": "A"}, {"sku": "B"}]}
```

`resolve_path(document, "items.sku")` 会得到 `"A"` 和 `"B"`。相比之下，通用 `get_path` 只返回一个值或 `MISSING`，不做查询展开。分离两个函数可以防止聚合与更新意外继承 matcher 专属的数组语义。

这是反复出现的架构经验：共享语法不等于共享基数。两个函数都理解点和数字数组下标，但只有 matcher 路径可返回多个候选。

## 与真实 MongoDB 对照

真实 MongoDB 存储二进制 BSON，并支持这里没有的 date、binary、decimal、regex、timestamp、MinKey、MaxKey 等类型。MiniMongoDB 的 tagged JSON 持久化易检查，但既非 BSON 二进制也不兼容线协议。MongoDB ObjectId 生成带非确定性和时间信息；本地计数器在来源语义上相反。

较窄的对应仍然有用：文档和数组仍是不同类型值；嵌入文档相等仍比较完整值并对字段顺序敏感；点记法仍选择嵌套字段，数字段仍可寻址数组位置。

准确边界见[BSON 与标识差异](../DIFFERENCES.md#bson-与标识差异)、[查询差异](../DIFFERENCES.md#查询差异)以及[映射表](../mapping.md#minimongodb--mongodb-映射)中的 `bson.types`、`ObjectId`、`bson.path` 行。

一个尤其重要的不一致是 null 与 missing：真实 MongoDB 中 `{field: null}` 也匹配字段缺失；MiniMongoDB 的 null 字面量相等要求存在 `None`，缺失要用 `$exists: false`。

## 动手实验：检查标签、顺序和路径

运行：

```bash
UV_CACHE_DIR=/tmp/minimongodb-uv-cache uv run python - <<'PY'
from minimongodb import ObjectId
from minimongodb.bson import MISSING, bson_compare, bson_equal, get_path, type_tag

values = [None, 1, "a", {"a": 1}, [1], False, ObjectId(1)]
print("tags:", [type_tag(value) for value in values])
print("ascending:", all(bson_compare(a, b) < 0 for a, b in zip(values, values[1:])))
print("True equals 1:", bson_equal(True, 1))
document = {"profile": {"names": [{"first": "Ada"}]}, "nullish": None}
print("nested:", get_path(document, "profile.names.0.first"))
print("missing sentinel:", get_path(document, "profile.city") is MISSING)
print("null is missing:", get_path(document, "nullish") is MISSING)
PY
```

实测输出：

```text
tags: ['null', 'number', 'string', 'document', 'array', 'bool', 'objectId']
ascending: True
True equals 1: False
nested: Ada
missing sentinel: True
null is missing: False
```

输出证明了项目专属标签顺序和 null/missing 区分，并不证明真实 BSON 比较对等。

## 练习

### 1. 理解题：相等还是选择？

为什么 `{"city": "London"}` 与 `{"city": "London", "role": "engineer"}` 的精确比较会失败，而 `profile.city` 点路径查询会成功？

??? note "参考答案"

    精确文档相等比较完整有序键值序列；点路径先选择嵌套 `city` 标量，无关的 `role` 不再进入被比较值。

### 2. 理解题：带类型标识

预测 `_id=True` 是否与 `_id=1` 冲突，以及 `_id=1` 是否与 `_id=1.0` 冲突，再用 `Collection.insert_one` 验证。

??? note "参考答案"

    `True` 与 `1` 标签不同，可以共存；普通 `1` 与 `1.0` 共享数值 BSON 相等性，会在 `_id` 索引冲突。验收是第一组两次插入成功，第二组抛出 `DuplicateKeyError`。

### 3. 动手题：在纸面上增加教学值类型

起草但不应用一个加入 `date` 标签的 diff。指出 `type_tag`、`_TYPE_ORDER`、相等/比较、`canonical_key` 和 storage codec 的改动。验收：提案覆盖每层，并至少包含一个 round-trip 测试和一个排序测试。

??? note "参考答案"

    完整提案应在 unsupported-value 拒绝前加入 `datetime` 检查，分配明确顺序，定义确定的同标签比较和 canonical 编码，在 `_to_node/_from_node` 加 `date` 分支，并测试 clone 校验、相等、比较、canonical `_id` 行为以及 checkpoint/journal round trip。只改 `type_tag` 不完整，因为持久化会拒绝新节点。

### 4. 动手题：不改源码操作路径

在本地字典上使用 `get_path`、`set_path`、`unset_path`。验收：创建 `profile.city`，修改 `names.0.first`，unset `values.1`，最终打印 `None` 占位而非缩短数组。

??? note "参考答案"

    从 `{"profile": {"names": [{"first": "Ada"}]}, "values": [1, 2, 3]}` 开始。操作后相关形状应为 `{"profile": {"names": [{"first": "Grace"}], "city": "London"}, "values": [1, None, 3]}`。

## 小结

MiniMongoDB 在 Python 容器之上覆盖了显式数据库语义。`type_tag`、`bson_equal`、`bson_compare`、`canonical_key` 让类型、相等、顺序和哈希标识保持一致。`get_path` 做单值文档遍历，matcher 的 `resolve_path` 则可能穿过数组展开。下一章将用这些原语解释全书核心查询课：数组何时展开为候选元素，何时保持为精确整体值。
