# 第 6 章：作为收敛日志的 Oplog

第 5 章建立了持久化顺序：MiniMongoDB 先把带帧的记录追加到 journal，
再把变更发布到内存。本章研究帧里的逻辑记录。人们常把 oplog 说成
“写操作列表”，但这句话掩盖了最重要的设计选择：日志应该记住客户端
请求的动作，还是副本最终必须到达的状态？MiniMongoDB 选择后者。

## 学习目标

学完本章，你将能够：

- 从 `Collection._update` 经 `Oplog.emit` 一直追踪到 `replay`；
- 解释 `$inc` 为什么在进入 oplog 前会改写成 `$set`；
- 预测 insert、replace、update、delete 记录被重复重放后的结果；
- 找出持久接收/内存发布边界，以及不会递归写日志的恢复路径；
- 区分 MiniMongoDB 的进程内逻辑 oplog、MongoDB 复制 oplog 与
  WiredTiger journal。

## 6.1 命令描述意图，oplog 记录描述收敛状态

设计数器当前为 `2`，客户端发送 `{"$inc": {"count": 3}}`。重复执行
该命令会得到 `8` 而非 `5`，所以它不是幂等操作。恢复节点却完全可能
再次遇到一个已经生效的记录：checkpoint 可能已包含其效果，传输可能
重复投递，调用者也可能故意重放同一输入。持久表示应让重复应用无害。

转换发生在 `src/minimongodb/collection.py` 的
`Collection._update`。它先在隔离副本上调用
`apply_operator_update`。完整候选文档构造完成且二级索引验证通过后，
`_update` 才调用 `Collection._post_image_update`：

```python
self.oplog.emit(
    self.name,
    "update",
    original["_id"],
    self._post_image_update(candidate, update),
)
```

`Collection._post_image_update` 不复制请求里的算子。它遍历这些算子
提到的每条路径，从最终候选文档读取值；值存在就生成 `$set`，路径缺失
就生成 `$unset`。因此请求的增量操作会变成
`{"$set": {"count": 5}}`，重复赋值仍收敛到 `5`。

这是一种“按变更路径记录的后像”，而不是完整文档后像。它比替换整个
文档更小，却仍然描述最终值。如果一个请求先 unset 再 set 同一路径，
函数只读取一次最终候选文档，并只记录最后的 `$set`。
`tests/test_oplog.py` 中
`test_post_image_keeps_only_the_final_state_for_a_repeated_path`
固定了这个合同。

这种区别不限于数据库。动作日志说“执行这个状态转换”，收敛日志说
“让这个具名状态等于该值”。后者更容易安全重试，但要求主节点先算出
结果，再记录日志。

## 6.2 记录形状与序号所有权

在 `src/minimongodb/oplog/entry.py` 中，`OplogEntry` 是带五个字段的
冻结 dataclass：`sequence`、`collection`、`operation`、`key` 和
可选 `payload`。Collection 方法会发布以下操作形状：

- `insert` 与 `replace` 携带完整结果文档；
- `update` 携带最终的 `$set`/`$unset` 赋值；
- `delete` 只携带标识键，没有 payload；
- `create_index` 携带可持久化的索引定义。

`Oplog.emit` 拥有序号分配权。它用当前 `_next_sequence` 构造记录，
克隆 payload 以跨越所有权边界，然后调用可选 listener。在
`Database` 中，该 listener 就是 journal append 路径。只有 listener
成功返回，`emit` 才把记录加入内存列表并递增序号。

```python
if self._listener is not None:
    self._listener(entry)
self._entries.append(entry)
self._next_sequence += 1
```

这个顺序不是装饰。持久追加失败时，既不消耗序号，也不发布记录。
回到 `Collection.insert_many`、`Collection._update` 或
`Collection._delete`，文档与索引变更同样发生在 `emit` 之后。因此
调用者看到的是一个已提交前缀：更早的逐文档记录可以已持久且可见，
失败文档及之后的文档则都不可见。这不是多文档事务。

oplog 对象本身是内存中的 append-only 列表。类文档字符串称其为
“v1”，并明确 capped retention 属于 M3。
`src/minimongodb/oplog/capped.py` 只有一个划定边界的文档字符串，
没有暴露伪造的 ring buffer。因此长期运行的 MiniMongoDB 进程不会
限制这个内存列表的大小。

## 6.3 重放故意走另一条写路径

`src/minimongodb/oplog/replay.py` 的 `replay` 接收记录迭代器，以及
单个目标 `Collection` 或 collection 名到对象的映射。它跳过序号
小于等于 `after_sequence` 的记录，把其余记录路由到对应 collection，
调用 `Collection._apply_oplog_entry`，最后返回见过的最大序号。
Database 启动时使用 checkpoint 保存的序号，只应用更新的 journal
记录。

关键在于 replay **没有**调用什么。它不调用公开的 `insert_one`、
`update_one` 或 `delete_one`，否则消费旧日志时又会发出新日志，造成
递归增长。它改用 `src/minimongodb/collection.py` 中的
`Collection._apply_oplog_entry`，直接改变文档和索引结构且不 emit。

每种操作都有收敛规则：

- Insert 和 replace 共用一个分支。键不存在就追加 payload，存在就
  替换当前文档。
- Update 在键不存在时忽略；键存在时，重复应用最终 `$set`/`$unset`
  仍得到相同状态。
- Delete 删除存在的文档；文档已经不存在时则无操作。
- `create_index` 委托给 `Collection._restore_index`；同名定义已安装
  时直接返回。

重放还维护自动 `_id` 索引和所有二级索引。insert/replace 会调用
`IdIndex.add` 或 `Collection._replace_at`；delete 会先移除索引
ownership，再移除文档。如果文档收敛而索引漂移，所谓幂等就没有意义。

这里有一个重要前提：输入流是有序、权威的历史。MiniMongoDB 不解决
双主冲突、因果乱序、term、rollback 或 majority commit。幂等只让
重复应用安全，并不会让任意乱序变得安全。

## 6.4 与真实 MongoDB 对照

真实 MongoDB 把复制记录存入 capped collection `local.oplog.rs`。
副本集成员 tail 该 oplog，跟踪 timestamp 与 term，维护 majority
commit 信息，并可能回滚分叉历史。更新记录格式带版本且远比本教学
模型丰富。MongoDB 还把存储引擎恢复 journal 与复制 oplog 分开。

MiniMongoDB 有意合并了两个角色：逻辑 `OplogEntry` 同时也是本地
持久 journal 的 frame payload。它只有整数序号，没有 wall clock、
term、副本身份、传输、选举、rollback 和有界保留。每个受影响文档
发出一条记录，所以 `update_many` 会暴露持久前缀，而不是一个原子的
oplog 事件。

精确边界记录在
[差异：操作日志](../DIFFERENCES.md#操作日志差异)与
[差异：存储与崩溃](../DIFFERENCES.md#存储与崩溃差异)。
Mapping 把 `OplogEntry` 归为“有意简化”，却把“用逻辑 oplog frame
充当存储 journal”归为“语义相反”。完整写链见
[MiniMongoDB ↔ MongoDB 映射](../mapping.md#一次写入如何穿过这个微型系统)。
应迁移的是收敛思想，而不是文件格式或运维保证。

## 6.5 动手实验：同一段历史重放两次

在仓库根目录运行。显式 cache 路径既适用于普通 shell，也适用于全局
cache 只读的开发沙箱。

```bash
UV_CACHE_DIR=/tmp/minimongodb-uv-cache uv run python labs/lab_oplog_idempotent.py
```

实测输出：

```text
requested $inc: {'$inc': {'count': 3}}
stored oplog payload: {'$set': {'count': 5}}
  Repeating $inc would add twice; repeating $set converges on count=5.
after one replay: [{'_id': 'visits', 'count': 5}]
after two replays: [{'_id': 'visits', 'count': 5}]
same after replay twice: True
```

前两行展示边界：公开更新语言包含动作，复制/持久语言包含赋值。后三行
证明的是状态收敛，而不只是返回码相等。

再运行聚焦的可执行合同：

```bash
UV_CACHE_DIR=/tmp/minimongodb-uv-cache uv run pytest -q tests/test_oplog.py
```

实测输出：

```text
.......                                                                  [100%]
7 passed in 0.05s
```

两个命令都不使用 socket 或外部 MongoDB 进程，均已通过仓库的直接
Python API 实测。

## 6.6 练习

### 理解题 1：动作与状态

当前文档为 `{"_id": 1, "n": 10}`，客户端请求
`{"$inc": {"n": 2}}`。update oplog payload 应包含什么？为什么保存
原请求不安全？

??? note "参考答案"
    应包含 `{"$set": {"n": 12}}`。重复 `$inc` 两次会到 `14`，重复
    `$set` 两次仍是 `12`。主节点在 emit 之前先计算 post-image。

### 理解题 2：发布失败

oplog listener 在接收序号 5 时抛异常。序号 5 的哪些部分可以变得
可见？下一次成功 emit 会尝试哪个序号？

??? note "参考答案"
    记录 5、它的文档变更和索引变更都不会可见。`Oplog.emit` 先调用
    listener，再 append 和递增；collection 变更又发生在 `emit`
    之后。所以下一次仍尝试序号 5，更早的已提交记录保留可见。

### 动手题 3：增加重放观察器

在临时分支上给 `replay` 增加可选 callback，只接收真正应用而非跳过
的记录，不改变公开 collection 写路径。验收：重放序号 1–3，设置
`after_sequence=1`，断言 callback 收到 `[2, 3]`；再运行
`uv run pytest -q tests/test_oplog.py`。

??? note "参考答案"
    最小概念 diff：

    ```diff
    -def replay(entries, target, *, after_sequence=0):
    +def replay(entries, target, *, after_sequence=0, on_apply=None):
         ...
         collection._apply_oplog_entry(entry)
    +    if on_apply is not None:
    +        on_apply(entry)
    ```

    callback 应放在成功应用之后，避免报告被跳过或失败的工作。验收
    测试收集 `entry.sequence`。本教程不会把该 diff 应用到 `src/`。

## 小结

MiniMongoDB 把非幂等客户端意图转换为逐路径后像赋值，先持久接收每条
记录再发布，并通过不写日志的内部路径重放。重复应用会收敛，但该模型
不提供乱序修复、副本集共识或多文档原子性。第 7 章沿用同一个发布
边界：一次写改变一个文档时，它的每个规范化二级索引键也必须随之收敛。
