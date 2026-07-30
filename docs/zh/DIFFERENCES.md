> **语言**: [English](../DIFFERENCES.md) | 简体中文

# 与 MongoDB 的差异

MiniMongoDB 是机制模型（mechanism model），而不是兼容性实现
（compatibility implementation）。本文档记录了该设计的非目标，以及 M2
及之前引入的较小语义差异。

## 明确的非目标

- 分片（sharding）、`mongos`、均衡器行为和分片键；
- 副本集（replica set）网络通信、选举、同步源选择和回滚；
- 多文档 ACID 事务、会话、读/写关注（read/write concern）和多版本并发控制
  （MVCC）；
- `$lookup`、变更流、TTL、文本、通配符、哈希和地理空间索引；
- MongoDB 线路协议（wire protocol）、驱动程序、身份认证、授权和服务器管理；
- 二进制 BSON 兼容性；
- WiredTiger 压缩、页面、缓存淘汰、并发和检查点；
- JavaScript 执行、模式验证、排序规则（collation）、正则表达式和完整 MQL。

## 里程碑边界

- **M1（已实现）：** 值/路径语义、CRUD、查询/更新子集、自动 `_id`、幂等
  操作日志（oplog）、日志、检查点、恢复和实验。
- **M2（已实现）：** 二级/复合/唯一/multikey 索引、前缀感知选择性、
  IXSCAN/COLLSCAN 规划、`explain` 和最小聚合管道。
- **M3（未实现）：** 封顶/环形操作日志保留，以及到 MiniDist 的复制映射。
  现在只有 `oplog/capped.py` 仍是文档边界。

## BSON 与标识差异

- 文档是 Python `dict` 值，数组是 `list` 值。支持的标量值为 `None`、bool、
  int/float、字符串和 MiniMongoDB `ObjectId`。日期、二进制、decimal、regex、
  timestamp、MinKey/MaxKey、code 及其他类型会被拒绝。
- 本地跨类型顺序为：
  `null < number < string < document < array < bool < objectId`。
  它刻意不是完整的 BSON 比较顺序。
- 内嵌文档的精确相等比较将字段插入顺序视为有意义。持久化使用有序键值对
  保留该顺序。
- 真实 ObjectId 包含非确定性或由环境派生的材料。MiniMongoDB 的 24 位十六
  进制类似物只是一个注入的单调计数器。
- `_id` 索引会递归转换为带 BSON 类型标签、可哈希的规范键。因此 `True` 与
  `1` 不同，而数值相等的 int/float 共用一个标识，与本项目的 `bson_equal`
  语义一致。

## 查询差异

- 仅实现了 `$eq`（包括隐式相等）、`$gt/$gte/$lt/$lte/$ne/$in/$exists/$and/$or/$not`。
- 字段级 `$not` 遵循所支持的 MongoDB 形状子集。MiniMongoDB 还接受顶层逻辑
  `$not`；真实 MongoDB 不支持顶层 `$not`。这是本项目扩展，不是可移植的
  MQL 行为。
- 标量相等和比较会递归检查所存数组的元素。字面量数组相等仍是整个数组的
  比较，并且顺序敏感。
- 字面量内嵌文档使用整个值的精确相等比较。请使用点分路径选择单个嵌套字段。
- 真实 MongoDB 的范围谓词通常使用类型界定（type bracketing）。MiniMongoDB
  则使用其有文档说明的全局顺序比较所支持的不同类型。
- MongoDB 的 `{field: null}` 也会匹配缺失字段。MiniMongoDB 区分 null 和
  缺失；对缺失字段请使用 `$exists: false`。
- 不提供 `$elemMatch`；因此，数组路径上的多个谓词可能由不同元素分别满足。
- `find` 不提供 projection、sort、skip、limit、cursor、collation 或 regex
  选项；即使 IXSCAN 缩小了候选集，它仍按插入顺序返回立即求值的列表。
  projection/sort/limit 只作为聚合 stage 提供。

## 索引与规划器差异

- 二级索引是仅升序的 canonical 有序映射，不是 B-tree。支持点分字段和复合
  最左前缀；不支持降序、稀疏、部分、通配符、哈希、文本或地理空间索引。
- 索引键与 `_id` 使用同一套递归 BSON 标签 canonical 形式。数组递归展开成
  逐元素 multikey 条目，同一文档拥有的重复键会去重。
- 当多个被索引字段都是数组时，复合索引会形成笛卡尔积。真实 MongoDB 会拒绝
  一个文档中超过一个索引字段为数组的复合 multikey 索引；本微型实现为了显式
  展示展开机制而保留乘积。
- 缺失字段使用类似 null 的键。没有 sparse 选项，因此 unique 索引对该
  missing/null 键只允许一个文档。
- 创建索引会先验证现有文档，追加持久的 `create_index` 条目，再发布定义。
  定义也进入 checkpoint；文档变更只有在 journal 成功后才更新全部索引。
- 规划器没有统计目录、直方图、计划缓存、索引交集、覆盖查询、排序满足或试运行。
  它统计前缀兼容索引的候选所有者，仅当候选数小于集合大小时选择 IXSCAN。
- 安全的 `_id` 相等查询使用自动 `_id_` IXSCAN。由于本教学模型仍允许根 `_id`
  为数组，只要存在这种 id，标量谓词就回退 COLLSCAN，避免丢失 matcher 的
  数组元素展开语义。
- `explain(query)` 是立即求值的集合方法，而不是 cursor 方法。它只报告一个
  胜出计划和 `keysExamined/docsExamined/nReturned`，没有 verbosity 模式、
  rejected plans、耗时、yield 或存储指标。

## 聚合差异

- 只实现 `$match/$project/$group/$sort/$limit`。`$match` 复用普通 matcher；
  不做管道改写或索引下推。
- `$group` 支持 `_id` 与 `$sum/$avg/$min/$max/$push`。表达式仅限常量、
  点分 `$field` 引用或嵌套文档/list 形状，不提供完整 MongoDB 表达式语言。
- `$match`、`$project`、`$limit` 流式执行；`$group`、`$sort` 在内存中物化
  输入。不提供 spill、并行、分布式 merge、`$lookup`、`$unwind`、窗口函数
  或优化器。

## 更新与 CRUD 差异

- 仅实现了 `$set/$unset/$inc/$push/$pull` 更新操作符。`$push` 不提供
  `$each/$slice/$sort/$position`；`$pull` 接受本地匹配器子集。
- 路径可以创建缺失的字典父级。路径绝不会凭空创建或扩展缺失数组；数字索引
  必须已经存在。
- 对数组索引执行 `$unset` 会写入 `None` 以保留位置，这与 MongoDB 的实用行为
  一致；取消设置文档键则会删除该键。
- 不提供更新插入（upsert）、数组过滤器（array filter）、位置 `$` 操作符、
  批量写入模式、find-and-modify 变体或写关注（write concern）。
- `insert_many` 会在任何文档可见之前验证整个批次。被拒绝批次已经消耗的
  计数器值不会回滚。
- `insert_many`、`update_many` 和 `delete_many` 不是全有或全无的持久化事务。
  `insert_many` 会先验证所有候选；随后每个批量方法都逐文档准备并提交。如果
  第 N 项追加日志失败，之前的项保持持久且可见，第 N 项及后续项保持不可见，
  失败的 sequence 不会被消耗，并抛出存储错误。
- 单文档变更仅在单个 Python 进程内是原子的：引擎先构建并验证副本，再进行
  交换。不提供并发读写者隔离。

## 操作日志差异

- MiniMongoDB 为每个受影响的文档生成一个条目（另有索引定义条目），而不是
  生成与 MongoDB 字节兼容的操作日志记录。
- 插入/替换记录携带完整文档。更新记录为每个请求的路径携带 `$set` 和
  `$unset` 后像；`$inc`、`$push` 和 `$pull` 永远不会保留到条目中。
- 当键已经不存在时，删除重放为空操作。插入/替换重放按 `_id` 收敛。
- 内存操作日志没有边界。封顶保留是 M3 的内容。
- 不提供任期、时间戳、墙上时钟、复制副本标识、多数派提交点、回滚或跨节点
  传输。

## 存储与崩溃差异

- 本地日志将逻辑操作日志条目封装为
  `4-byte length | payload | 4-byte CRC32`。真实 MongoDB 使用 WiredTiger
  存储引擎日志，并将其与复制操作日志分离。
- 在文档、`_id`/二级索引、sequence 或内存 oplog 条目可见之前，追加操作会刷新
  并执行 `fsync`。失败的追加会尽力截断回原边界并抛出存储错误。不提供组提交
  （group commit）。
- 只有无效的最终帧会通过截断到最后一个有效前缀来修复。如果后面仍有字节，
  在它们之前发生的 CRC/解码失败会引发损坏错误，而不是静默丢弃历史记录。
- 检查点将整个数据库序列化为带标签的 JSON，原子替换一个文件，并在 rename
  后对父目录执行 `fsync`。它不提供独立校验和、页面、压缩、模糊检查点协议
  （fuzzy checkpoint protocol）或并发写入协调。
- 启动时加载检查点，并且只重放序列号比快照更新的日志。重放不会递归追加
  新记录。
- 公开的 `inject_journal_tail_truncation` 方法仅用于确定性的教学实验和测试；
  它不是数据库管理功能。
