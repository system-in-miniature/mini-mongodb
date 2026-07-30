# 第 4 章：动手实验

[English](../labs-guide.md)

先执行 `uv sync`，再从仓库根目录运行命令。lab 只使用公开 API；崩溃恢复实验
使用临时目录，不会在仓库内留下数据库文件。

## 数组与嵌套文档匹配

源码：
[lab_array_matching.py](https://github.com/system-in-miniature/MiniMongoDB/blob/main/labs/lab_array_matching.py)

```bash
uv run python labs/lab_array_matching.py
```

预期：标量数组查询与点分路径查询都打印 `['Ada']`，不完整嵌套文档字面量打印
`[]`。重点区分数组元素遍历、整个文档精确相等和显式点分字段选择。

## 幂等 oplog 重放

源码：
[lab_oplog_idempotent.py](https://github.com/system-in-miniature/MiniMongoDB/blob/main/labs/lab_oplog_idempotent.py)

```bash
uv run python labs/lab_oplog_idempotent.py
```

预期：请求的 `{'$inc': {'count': 3}}` 被记录为
`{'$set': {'count': 5}}`；重放一次或两次都得到 count 为 `5` 的同一文档。
重点观察 oplog 为什么记录可收敛的后像，而不是原始的非幂等动作。

## journal 尾部撕裂恢复

源码：
[lab_crash_recovery.py](https://github.com/system-in-miniature/MiniMongoDB/blob/main/labs/lab_crash_recovery.py)

```bash
uv run python labs/lab_crash_recovery.py
```

预期：截断前文档 `1`、`2` 都可见；重启后只保留已 checkpoint 的文档 `1`，
不完整的最后 journal 帧被丢弃。剩余字节数是实现细节。重点观察原子 checkpoint
与有效 journal 帧前缀之间的恢复边界。

## Multikey 索引展开

源码：
[lab_multikey_index.py](https://github.com/system-in-miniature/mini-mongodb/blob/main/labs/lab_multikey_index.py)

```bash
uv run python labs/lab_multikey_index.py
```

预期：`tags` 索引报告 `multikey: True`，三个文档共生成四个不同索引键；
查询 `"database"` 返回文档 id `[1, 2]`。重点观察一个含数组的文档如何拥有
多个 canonical 键，以及同一文档内的重复值如何去重。

## 建索引前后的 explain

源码：
[lab_explain.py](https://github.com/system-in-miniature/mini-mongodb/blob/main/labs/lab_explain.py)

```bash
uv run python labs/lab_explain.py
```

预期：同一个选择性查询从检查四个文档的 `COLLSCAN` 变为只检查一个文档的
`IXSCAN`。matcher 和返回结果不变；改变的只是规划器的候选来源与扫描工作量。

继续阅读 [MongoDB 映射](mapping.md)和[已声明差异](DIFFERENCES.md)。
