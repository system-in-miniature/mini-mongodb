# MiniMongoDB：微缩文档数据库

[English](../index.md)

MiniMongoDB 是一个确定性的单进程 Python 内核，用来学习文档数据库如何拥有值、
匹配数组、执行单文档原子更新、持久化写入、重放 oplog、维护 multikey 索引、
选择查询计划并执行聚合管道。

本书按机制依赖顺序展开。每章都把论断锚定到 `src/minimongodb/` 下的具体函数，
对照真实 MongoDB，提供带实测输出的实验，并以练习收束；练习中的源码改动只以
提案形式呈现，不落到 `src/`。

## 开始之前

需要 Python 3.12+ 和 [uv](https://docs.astral.sh/uv/)：

```bash
git clone https://github.com/system-in-miniature/mini-mongodb.git
cd mini-mongodb
uv sync
uv run pytest -q
```

MiniMongoDB 是进程内教学内核，不是 MongoDB 兼容服务器；它没有 MongoDB 线协议
或驱动端点。阅读时请同时参考[机制映射](mapping.md)与[差异](DIFFERENCES.md)，
始终把等价、有意简化和语义相反的行为分开。

## 全书目录

1. [认识 MiniMongoDB](tutorial/01-getting-started.md)——定位、环境、第一次
   `insert`/`find` 和完整系统地图。
2. [文档模型](tutorial/02-document-model.md)——BSON 形状类型标签、比较序、
   带类型标识和点路径。
3. [查询语义](tutorial/03-queries.md)——查询算子，以及数组展开、整体精确值、
   点路径之间的关键区别。
4. [更新算子](tutorial/04-updates.md)——`$set/$inc/$push/$pull`、替换更新、
   不可变 `_id` 和 copy-first 原子性。
5. [持久性与恢复](tutorial/05-durability.md)——journal-first 发布、
   committed prefix、checkpoint 和启动恢复。
6. [Oplog](tutorial/06-oplog.md)——后像改写，以及把 `$inc` 重放为 `$set`
   为什么能得到幂等恢复。
7. [二级索引](tutorial/07-secondary-indexes.md)——由 canonical 类型键构建的
   compound、unique 与 multikey 索引。
8. [规划与 Explain](tutorial/08-planner-explain.md)——IXSCAN 与 COLLSCAN、
   最左前缀、选择性和扫描计数。
9. [聚合管道](tutorial/09-aggregation.md)——把
   `$match/$project/$group/$sort/$limit` 理解为流式与阻塞 stage。
10. [关系模型与文档模型](tutorial/10-relational-vs-document.md)——与
    MiniPostgres 的系统对照，以及两种模型各自的边界。

## 参考资料

[仓库中文 README](https://github.com/system-in-miniature/mini-mongodb/blob/main/README.zh-CN.md)
给出已实现能力清单和源码目录导览；[机制映射](mapping.md)是 parity 账本；
[差异](DIFFERENCES.md)定义语义边界；[实验指南](labs-guide.md)汇集可运行演示。
建设期计划保留在[设计历史存档](../superpowers/README.md)，但行为由教程、当前
源码和测试共同定义。
