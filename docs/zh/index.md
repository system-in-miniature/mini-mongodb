# MiniMongoDB 教程

[English](../index.md)

MiniMongoDB 是一个确定性的单进程 Python 文档数据库内核，用来学习点分路径、
数组感知匹配、canonical multikey 索引、COLLSCAN/IXSCAN 规划、聚合管道、
幂等后像 oplog、CRC 分帧 journal、checkpoint 与启动恢复。它不是 MongoDB
兼容服务器。

## 安装

需要 Python 3.12+ 和 [uv](https://docs.astral.sh/uv/)。

```bash
git clone https://github.com/system-in-miniature/MiniMongoDB.git
cd MiniMongoDB
uv sync
```

## 第一个实验

```bash
uv run python labs/lab_array_matching.py
```

输出会展示：标量谓词可匹配已存数组的元素；不完整的嵌套文档字面量不等于整个
文档；点分路径则直接选择嵌套字段。

## 阅读顺序

先看仓库的端到端数据路径和目录导览，再读映射、运行五个 lab，最后通过差异章节
把这个 M2 教学模型与生产 MongoDB 语义分开。

完整实现范围与持久化 API 示例见
[中文 README](https://github.com/system-in-miniature/MiniMongoDB/blob/main/README.zh-CN.md)。
[设计历史存档](../superpowers/README.md)记录建设期计划；正典文档与测试定义当前行为。
