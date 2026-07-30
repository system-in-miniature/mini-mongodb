> **语言**: [English](../mapping.md) | 简体中文

# MiniMongoDB ↔ MongoDB 映射

`Level`（级别）列是教学约定的一部分：

- **Equivalent** 表示本地机制保留了指定的核心不变量（core invariant），并不
  表示其性能或实现与生产系统等同（production-equivalent）。
- **Intentionally simplified** 表示方向相同，但接口表面或底层机制更小。
- **Semantically opposite** 表示这个微型系统刻意反转了真实系统中的一项重要
  选择；绝不要通过类比迁移该行为。

| MiniMongoDB 模块 | 真实 MongoDB 概念/子系统 | 级别 | 应迁移的认识 |
|---|---|---|---|
| `bson.types.ObjectId` | BSON ObjectId 标识值 | 语义相反（Semantically opposite） | 两者都是 12 字节形态的标识，但真实 ObjectId 会编码时间、进程、随机值和计数器材料；本项目禁用这些来源，只使用一个注入的计数器。 |
| `bson.types` 字典/列表模型 | 二进制 BSON 值与比较顺序 | 有意简化（Intentionally simplified） | 值仍带有类型，文档与数组仍彼此有别。支持的类型和跨类型顺序要少得多。 |
| `bson.path` | MQL 点分字段路径 | 有意简化 | 嵌套字段和显式数字数组索引共用一种路径表示法；此处拒绝有歧义的稀疏数组创建。 |
| `query.matcher` 标量与数组的相等判断 | MQL 多键匹配行为 | 等价（Equivalent） | 标量谓词无需显式迭代即可匹配已存储数组中的一个元素。 |
| `query.matcher` 字面量文档相等判断 | BSON 嵌入式文档相等判断 | 等价 | 字面量嵌入式文档作为完整值比较，包括字段顺序；点分路径选择单个嵌套字段。 |
| `query.matcher` 范围比较 | MQL 比较谓词 | 语义相反 | MongoDB 通常对范围谓词应用类型限定（type bracketing）；MiniMongoDB 则跨所有受支持类型公开其全局教学顺序。 |
| `query.matcher` 顶层 `$not` | 字段级 `$not` 查询操作符 | 语义相反 | MiniMongoDB 接受项目特有的顶层逻辑 `$not`；真实 MongoDB 只支持字段操作符 `$not`，并拒绝顶层形式。 |
| `update.operators` | MQL 更新修饰符 | 有意简化 | 替换更新与操作符更新相互分离；路径变更在单文档内具有原子性。不支持操作符选项和数组过滤器。 |
| `index.IdIndex` | 自动创建的唯一 `_id_` 索引 | 等价 | 每个集合都会在写入可见前按带 BSON 类型的相等语义保证标识唯一。底层使用带规范标签键的 Python 哈希映射，而非 B-tree。 |
| `index.SecondaryIndex` | 升序二级、复合、唯一和 multikey 索引 | 有意简化 | 点分字段与 `_id` 共用带 BSON 标签的 canonical 相等语义；含数组的文档拥有多个去重键。复合扫描要求最左前缀。本地有序映射不是 B-tree，也不实现降序、稀疏、部分或专用索引。 |
| `collection.Collection` | 集合 CRUD 层 | 有意简化 | 文档会跨越复制边界，并且仅在日志条目持久化后发布。批量方法提交前缀，而不是充当多文档事务。 |
| `oplog.OplogEntry` | 副本集 oplog 后镜像/幂等规约 | 有意简化 | 动作更新变为可安全重复的最终赋值。真实 oplog 格式和各版本专用的更新编码更为丰富。 |
| 携带 oplog 帧的 `storage.journal` | WiredTiger 日志加副本 oplog | 语义相反 | 真实 MongoDB 将存储引擎恢复记录与复制 oplog 分离；M1 复用逻辑 oplog 条目作为本地持久化日志。 |
| `storage.checkpoint` | WiredTiger 检查点 | 有意简化 | 重启时从快照开始，并应用更新的持久化记录。该快照是带类型标签的全数据库 JSON，没有页或 MVCC。 |
| `storage.recovery` | 启动恢复 | 等价 | 只重放 CRC 有效的日志前缀；重复应用已经应用过的后镜像不会造成影响。 |
| `plan.choose_plan` | 查询规划器与 `explain` | 有意简化 | 前缀兼容索引按候选文档所有权估计选择性；只有 IXSCAN 检查更少文档时才胜过 COLLSCAN。explain 返回 Mongo 术语的胜出 stage 与实际键/文档计数。 |
| `aggregate.execute_pipeline` | 聚合管道执行 | 有意简化 | `$match/$project/$group/$sort/$limit` 组成文档算子流；group 支持 `$sum/$avg/$min/$max/$push`。流式与阻塞 stage 边界显式存在，但没有 MongoDB 优化器或分布式管道。 |
| `oplog.capped` 文档字符串 | 有界 `local.oplog.rs` 保留机制 | 有意简化 | 接口方向已记录，但有界保留是明确的 M3 工作项。 |

## 一次写入如何经过这个微型系统

```text
update_one({"_id": 1}, {"$inc": {"visits": 1}})
  → matcher selects one document
  → update engine mutates an isolated copy
  → immutable _id is validated
  → oplog prepares {"$set": {"visits": <final value>}}
  → journal appends length | payload | CRC and fsyncs
  → oplog publishes its sequence and in-memory entry
  → collection swaps the copy and all indexes atomically
```

关键的所有权边界（ownership boundary）位于用户命令与持久化条目之间。
命令说明*要尝试什么动作*；条目说明*要收敛到哪个最终状态*。

## 关系算子与文档管道

MiniPostgres 把针对 schema 行的 SQL 解析为计划树，Volcano 算子从子节点拉取
tuple。MiniMongoDB 从已经成形的查询文档出发，选择 `IXSCAN` 或 `COLLSCAN`，
再让自描述的嵌套文档依次通过聚合 stage。两者都教学算子组合与阻塞边界
（`Sort`/`Aggregate` 对 `$sort/$group`）；只有关系侧把列绑定到 schema，
文档侧则把点分路径与 multikey 扇出保留为运行时值语义。
