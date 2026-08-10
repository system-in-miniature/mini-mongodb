# MiniMongoDB Planner 工作量报告

在选择率固定为 1% 的 100、1,000、10,000 文档夹具上，COLLSCAN 检查全部文档，
`kind_1` IXSCAN 只检查命中的 1%。10,000 文档时，Docs Examined 从 10,000
降至 100，确定性工作量减少 100 倍；建索引前后的结果列表完全一致。

这是 Python 教学内核内部的 Explain 计数对比，不是耗时加速或生产 MongoDB
容量声明。
