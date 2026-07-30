# 第 1 章：认识 MiniMongoDB

[English](../../tutorial/01-getting-started.md)

MiniMongoDB 是一个用 Python 编写的小型、确定性文档数据库内核。它特意保留了足够多的数据库机制：类型化值、数组感知查询、更新算子、索引、规划器、oplog、journal、checkpoint、恢复和聚合；同时又足够小，让一个读者可以独自追踪一次写入如何从 API 到达持久化字节。它不是 MongoDB 服务器，也没有实现 MongoDB 线协议。

## 学习目标

学完本章，你将能够：

- 创建内存 `Collection`，插入文档并进行查询；
- 解释 MiniMongoDB 为什么在 API 的两个方向都复制文档；
- 把公开的 `insert_one`、`find` 调用追踪到具体源码函数；
- 区分教学机制模型与兼容服务器；
- 找到后续章节要研究的各个主要子系统。

## 为什么从微缩实现学习？

生产 MongoDB 包含网络、认证、复制、分片、事务、查询优化器、存储引擎、运维工具以及多年积累的兼容行为。这些能力在生产环境不可或缺，却会让第一次源码阅读变得困难：一次插入在底层思想显现之前就要跨过许多边界。

MiniMongoDB 去掉的是部署规模，而不是因果链。文档仍要跨越所有权边界；标识仍要在发布前检查；持久化数据库仍要先记录变更、再让变更可见；恢复仍要组合 checkpoint 与较新的日志记录。这个微缩实现的价值，在于这些决定表现为短小的 Python 函数，而不是庞大的分布式调用图。

这一区分决定了全书的阅读方式。不要问“能否把官方 MongoDB 驱动直接连到这个包”，答案是否定的。应该问：“这个小函数显式维护了什么不变量？生产数据库为什么需要更复杂的实现？”[映射表](../mapping.md)把每项对应关系标为“等价”“有意简化”或“语义相反”；[差异参考](../DIFFERENCES.md)记录了省略项和不可移植语义。

## 第一个 API 边界

公开接口集中在 `src/minimongodb/__init__.py`。应用通常从临时内存模型 `Collection` 或目录持久化模型 `Database` 开始。`InsertOneResult`、`UpdateResult` 等结果对象看起来像驱动结果，但并不冒充 PyMongo 类。

第一条重要路径是 `src/minimongodb/collection.py::Collection.insert_one`。即使只有一个文档，它也委托给 `Collection.insert_many`：

```python
def insert_one(self, document):
    return InsertOneResult(self.insert_many([document]).inserted_ids[0])
```

因此单条和批量插入共享相同的校验、标识、日志与发布规则。在 `Collection.insert_many` 中，每个输入先经过 `src/minimongodb/bson/types.py::clone_document`。该函数校验完整的受支持 BSON 形状树，再执行深复制。若没有 `_id`，集合会调用注入的 `CounterObjectIdGenerator`，随后计算带类型的 canonical key 并检查唯一 `_id` 索引。

复制不是装饰。没有复制，下面的代码会破坏存储：

```python
source = {"profile": {"city": "London"}}
collection.insert_one(source)
source["profile"]["city"] = "changed elsewhere"
```

MiniMongoDB 持有自己的副本，所以调用者后续的修改不会改变已存状态。读路径再次建立边界：`Collection.find` 调用 `Collection._run_query`，然后复制每个匹配文档再返回。调用者可以修改结果而不会修改数据库。这两个副本是对真实客户端与服务器之间序列化、缓冲区所有权边界的显式教学替代。

## 插入、发布，然后查询

校验之后，`Collection.insert_many` 按输入顺序处理候选文档。每个候选先调用 `src/minimongodb/oplog/entry.py::Oplog.emit`，随后追加到 `_documents`，加入 `IdIndex`，并更新二级索引。纯内存集合没有 journal listener，因此 `emit` 直接记录到本地 oplog。目录持久化 `Database` 则把 `src/minimongodb/storage/journal.py::Journal.append` 作为 listener；第 5 章会解释这为何改变发布边界。

查询进入 `src/minimongodb/collection.py::Collection._run_query`。它先用空文档调用 `src/minimongodb/query/matcher.py::matches`，确保即使集合为空也会校验查询语法；然后向 `src/minimongodb/plan/__init__.py::choose_plan` 请求 COLLSCAN 或 IXSCAN。无论候选来自哪里，最终都由同一个 `matches` 函数决定语义。规划只能减少工作，不能改变匹配集合。结果保持插入顺序，使实验和测试可重复。

这已经构成完整的数据库形状闭环：

```text
调用者文档
  -> 校验并复制
  -> 分配/检查 _id
  -> 发出变更
  -> 发布文档与索引
  -> 规划查询
  -> 匹配候选
  -> 复制返回文档
```

确定性贯穿整个项目。`CounterObjectIdGenerator` 产生可预测标识，集合存储保留插入顺序，oplog sequence 从已知值开始，实验避免时钟竞争。确定性不意味着生产 MongoDB 也如此；它意味着同一实验每次都能展示同一机制。

## 全书地图

接下来四章覆盖读写基础。第 2 章研究文档模型：显式类型标签、相等性、比较和点路径。第 3 章沿查询求值前进，重点区分数组上的标量谓词、整体数组字面量、嵌入文档字面量和点路径。第 4 章研究算子更新与替换更新，包括不可变 `_id`。第 5 章从内存集合进入 journal-first 持久性、checkpoint 和崩溃恢复。

后半部分建立在这些不变量之上。第 6 章解释为什么 `$inc` 等动作更新会成为 oplog 中幂等的后像；第 7、8 章覆盖二级索引、multikey 展开、规划和 `explain`；第 9 章把聚合视作流式与阻塞文档算子的链；第 10 章比较文档模型与关系模型，并以微缩实现推理的边界收束。

目录结构与这条路线一致：

- `bson/` 拥有值标识、比较、复制和路径；
- `query/` 决定文档是否匹配查询；
- `update/` 在不修改存储原件的前提下计算新文档；
- `collection.py` 协调 CRUD、日志、索引和查询执行；
- `oplog/` 表示可安全重复的逻辑变更；
- `storage/` 负责编码、journal 帧、checkpoint 和恢复；
- `index/`、`plan/` 在不重定义匹配的前提下缩小候选集；
- `aggregate/` 组合文档到文档的管道 stage。

遇到意外行为时，先寻找所有者再改代码。数组匹配属于 matcher，而非 planner；持久接受应发生在集合发布之前，而不是索引更新之后。这个所有权地图比死记单个方法更有价值。

## 与真实 MongoDB 对照

最接近的真实操作是一次 `insertOne()` 后接 `find()`。真实客户端通过 MongoDB 线协议向 `mongod` 发送 BSON 命令，随后还有服务端命令处理、授权、并发控制、复制和 WiredTiger。MiniMongoDB 是进程内 Python API，没有 socket、驱动 session、read concern、write concern，也没有并发读写隔离。

它的文档是 Python 字典和列表，而不是二进制 BSON；ObjectId 形状的值是确定性计数器，不是生产 ObjectId；内存列表不是 WiredTiger；结果类是教学接口，不是驱动兼容承诺。参见[ BSON 与标识差异](../DIFFERENCES.md#bson-与标识差异)、[更新与 CRUD 差异](../DIFFERENCES.md#更新与-crud-差异)以及[映射表](../mapping.md#minimongodb--mongodb-映射)中的 `collection.Collection` 行。

这些差异不是脚注，而是每个推论的准确边界：本仓可以教授所有权、校验顺序、标识与匹配；不能证明线协议兼容、分布式持久性或生产性能。

## 动手实验：第一次对话

在仓库根目录运行。普通可写环境可以省略 `UV_CACHE_DIR=...`；这里保留它，是因为默认 uv 缓存只读时也能运行。

```bash
UV_CACHE_DIR=/tmp/minimongodb-uv-cache uv run python - <<'PY'
from minimongodb import Collection, CounterObjectIdGenerator
people = Collection("people", id_generator=CounterObjectIdGenerator(7))
result = people.insert_one({"name": "Ada", "skills": ["Python", "databases"]})
print("inserted:", result.inserted_id)
print("found:", people.find({"skills": "Python"}))
PY
```

实测输出：

```text
inserted: 000000000000000000000007
found: [{'name': 'Ada', 'skills': ['Python', 'databases'], '_id': ObjectId('000000000000000000000007')}]
```

注入生成器解释了稳定标识。查询操作数是标量，而存储值是数组；matcher 会检查数组元素，所以 `"Python"` 匹配。第 3 章会从源码推导这条规则。

这是 direct API 实验，不包含网络或 socket 验证，因此不能作为 MongoDB 驱动兼容证据。

## 练习

### 1. 理解题：为什么复制两次？

解释 MiniMongoDB 为什么插入时复制、查询返回时又复制。答案应指出两次复制分别保护哪两个所有者。

??? note "参考答案"

    插入复制防止调用者拥有的可变对象直接成为数据库存储；查询复制防止数据库拥有的嵌套对象泄露给调用者。两者共同建立双向所有权边界。

### 2. 动手题：证明读隔离

编写内联 `uv run python` 实验：插入嵌套文档，修改 `find_one` 返回的对象，再打印第二次 `find_one`。验收：第二次结果必须保留原始嵌套值；不得修改 `src/`。

??? note "参考答案"

    ```bash
    uv run python - <<'PY'
    from minimongodb import Collection
    c = Collection()
    c.insert_one({"_id": 1, "nested": {"value": "stored"}})
    result = c.find_one({"_id": 1})
    result["nested"]["value"] = "caller"
    print(c.find_one({"_id": 1}))
    PY
    ```

    验收输出为 `{'_id': 1, 'nested': {'value': 'stored'}}`。

### 3. 动手题：检查确定性插入顺序

插入三个显式标识文档，查询全部并打印标识。验收：若插入顺序为 3、1、2，输出必须是 `[3, 1, 2]`，证明的是公开确定性顺序合同，而不是排序查询。

??? note "参考答案"

    使用 `Collection.insert_many([{"_id": 3}, {"_id": 1}, {"_id": 2}])`，再打印 `[doc["_id"] for doc in collection.find()]`。预期输出为 `[3, 1, 2]`。生产 MongoDB 并不把这种自然顺序作为通用合同。

## 小结

MiniMongoDB 的价值在于：用确定、可检查的 Python 保留数据库机制，并替代生产规模。`Collection.insert_one` 校验并复制文档、建立标识、发出变更、发布状态；`find` 规划、匹配，再返回新副本。下一章将打开二者之下的值层：哪些 BSON 形状值受支持，相等性为何不同于 Python 相等性，以及点路径如何穿过文档。
