# 自主重建

每个 Stage 都是一节可独立浏览的完整课：先理解当前问题、基本概念与必要性，再按机制板块连接相关文件和关键语句，最后用验证证据和自己的话完成理解闭环。

这是三种学习模式中的浏览器自主学习路径。按主题学习请进入[机制教程](../index.md)；需要 CLI 互动请查看 [Agent 带教使用教程](../agent-guide.md)。

如果希望在编辑器里聚焦当前增量，运行 `python -m journey.tools.build_journey study N`，再打开 `../MiniMongoDB-journey-workspace`。

| Stage | 主题 | 新增测试 | 教材章节 |
|---:|---|---:|---:|
| [01](stage-01.md) | BSON 值与点路径 | 1 | [2](../tutorial/02-document-model.md) |
| [02](stage-02.md) | 数组感知的查询匹配 | 2 | [3](../tutorial/03-queries.md) |
| [03](stage-03.md) | 持久化 Oplog 帧 | 1 | [5](../tutorial/05-durability.md) |
| [04](stage-04.md) | CRUD、更新与恢复闭环 | 4 | [6](../tutorial/06-oplog.md) |
| [05](stage-05.md) | 日志优先与身份边界 | 4 | [5](../tutorial/05-durability.md) |
| [06](stage-06.md) | 索引计划与聚合管道 | 3 | [8](../tutorial/08-planner-explain.md) |
| [07](stage-07.md) | 规划前的查询校验 | 1 | [3](../tutorial/03-queries.md) |
| [08](stage-08.md) | 可执行领域实验 | 1 | [10](../tutorial/10-relational-vs-document.md) |
