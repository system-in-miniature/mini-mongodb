# 第 5 章：持久性与恢复

[English](../../tutorial/05-durability.md)

内存集合改变 Python 对象后即可宣布成功；持久化数据库需要更强边界：确认变更后，即使进程在 checkpoint 前死亡，重启也必须重建它。MiniMongoDB 用 fsync 的逻辑 journal 帧、全库 checkpoint 和前缀恢复实现这一边界。

## 学习目标

学完本章，你将能够：

- 从 `Database` 到 `Collection` 追踪 journal-first 发布；
- 描述 length/payload/CRC 帧和尾部修复规则；
- 解释 checkpoint 的临时写、fsync、rename、目录 fsync 顺序；
- 从 checkpoint sequence 与较新 journal entry 推导启动状态；
- 区分 batch committed-prefix 行为与事务；
- 说明哪些持久性论断不能转移到真实 MongoDB。

## 把持久性接入集合

`src/minimongodb/database.py::Database.__init__` 拥有一个目录、一个 `Journal`、一个全库 `Oplog` 和多个命名 `Collection`。关键接线是：

```python
self._journal = Journal(self.directory / "journal.bin")
self.oplog = Oplog(
    start_sequence=highest_sequence + 1,
    listener=self._journal.append,
)
```

数据库创建的每个集合都接收同一 oplog。集合变更调用 `src/minimongodb/oplog/entry.py::Oplog.emit`。`emit` 构造下一个不可变 `OplogEntry`，但在追加内存 entry list 或推进 sequence 前先调用 listener。

listener 是 `src/minimongodb/storage/journal.py::Journal.append`。只有 `append` 返回后，`Oplog.emit` 才发布 entry 并消耗 sequence；只有 `emit` 返回后，`Collection.insert_many/_update/_delete` 才发布文档与索引变化。调用顺序就是 journal-first 不变量：

```text
候选变更
  -> 编码 journal entry
  -> 追加完整 frame
  -> flush + fsync
  -> 发布内存 oplog/sequence
  -> 发布文档与索引
```

若 open、write 或 fsync 失败，存储异常向上传递，变更不可见，sequence 不被消耗。`Journal.append` 记录旧文件大小，失败时尝试 `_rollback_append`，truncate 并 fsync 回最后边界。回滚是 best-effort；若清理也失败，启动时的尾部修复是最后防线。

## 帧结构与损坏策略

`Journal.append` 从 `src/minimongodb/storage/codec.py::encode_entry` 获得确定性字节。codec 把每个受支持值变成 tagged JSON node，保留类型与文档字段顺序。entry 形状为：

```text
4-byte big-endian payload length | payload | 4-byte CRC32(payload)
```

length 定位 frame 边界，CRC 检测不完整或损坏内容。`src/minimongodb/storage/journal.py::Journal.read_entries` 从 offset 0 扫描，只接受完整、CRC 有效、可解码的 frame。

修复非常保守。最终 frame 中不完整 length、payload、坏 CRC 或不可解码 payload 可能是崩溃撕裂尾。开启 repair 后，`_repair_or_raise` 把文件截到最后有效 frame 边界，flush、fsync，再返回有效 entries。

若同样错误后面还有字节，就不能视为无害尾部。非最终 CRC/decode 错误抛 `JournalCorruptionError`。静默丢掉中间 frame 会保留缺少因果前驱的后续变更，可能制造非法历史。前缀恢复信任连续有效前缀，而不是每个可单独解码的碎片。

CRC32 检测意外损坏，不是密码学认证，无法防恶意篡改。项目没有 group commit、可配置 sync 策略、segment rotation 或后台 writer。

## 发布 checkpoint

不断增长的 journal 可以正确 replay，但越来越慢。`src/minimongodb/database.py::Database.checkpoint` 收集全库状态：当前 oplog sequence、所有集合文档和二级索引定义。索引 entry 本身不序列化；恢复时从定义和文档重建。

`src/minimongodb/storage/checkpoint.py::write_checkpoint` 编码状态并写 `checkpoint.bin.tmp`，flush 并 fsync 临时文件，调用 `os.replace` 原子发布为 `checkpoint.bin`，最后打开并 fsync 父目录。

为什么 fsync 目录？rename 修改目录元数据，只 fsync 文件不一定使新目录项在掉电后持久。目标顺序是：

```text
写临时 snapshot
  -> flush + fsync 临时文件
  -> 原子 replace 目标
  -> fsync 父目录
```

checkpoint 没有独立 checksum。它是完整 tagged-JSON 镜像，不是并发页面的 fuzzy snapshot。`Database` 明确是 single-writer，checkpoint 也没有并发写协调。

## 启动恢复

`src/minimongodb/storage/recovery.py::load_recovery_state` 读取 checkpoint（没有则给空状态），再读取并修复 journal 有效前缀；它本身不修改集合。

`Database.__init__` 把下一个 oplog sequence 设为 checkpoint sequence 和所有有效 journal entry 之上的值；还扫描恢复出的标识，防止确定性 ObjectId counter 重用旧值。集合名来自 checkpoint 文档、索引定义和 journal entry。

恢复分三阶段：

1. 用合成 insert entry 经 `Collection._apply_oplog_entry` 重建 checkpoint 文档；
2. 恢复 checkpoint 索引定义，并从文档重建 entries；
3. 调用 `src/minimongodb/oplog/replay.py::replay`，应用 sequence 大于 checkpoint 的 journal entries。

`_apply_oplog_entry` 是 recovery-only 路径，不会产生新日志。insert/replace 按 `_id` 收敛；update 后像应用最终 `$set/$unset`；删除已不存在 key 是 no-op。因此反复打开同一数据库不会在 replay 时追加 entry。

`after_sequence` 过滤正确连接 checkpoint 与 journal。checkpoint 后 journal 不截断，可能仍含 snapshot 已表示的记录；只重放较新 sequence 避免重复工作。幂等后像是额外安全性质，不替代 sequence 边界。

## 批量部分失败

`Collection.insert_many` 在发布前校验候选文档和唯一性，但之后逐文档 emit 并 publish；update-many、delete-many 也逐文档变更。若第三个 journal append 失败：

- 第一、二项已持久且可见；
- 第三项不可见，其 sequence 可复用；
- 后续项尚未尝试；
- 存储错误抛给调用者。

这个 committed-prefix 合同见[更新与 CRUD 差异](../DIFFERENCES.md#更新与-crud-差异)。它强于失控的部分修改，因为可见前缀与持久 frame 对齐；弱于多文档事务。调用者重试 batch 时必须处理已提交前缀。

## 与真实 MongoDB 对照

真实 MongoDB 把 WiredTiger recovery journal 与 replica-set oplog 分离。MiniMongoDB 复用逻辑 oplog entry 作为本地恢复记录，这是[映射表](../mapping.md#minimongodb--mongodb-映射)明确标注的语义相反架构。真实系统还有 page、WAL 细节、group commit、压缩、并发 checkpoint、recovery timestamp、write concern、复制 commit point 和更丰富故障处理。

可迁移的是顺序与前缀推理：变更必须先跨过持久接受边界，才能发布易失状态；snapshot 必须原子发布；重启从 checkpoint 开始并应用较新的有效日志。这里的 codec 与文件布局只是教学装置，不是 MongoDB 格式。

参见[存储与崩溃差异](../DIFFERENCES.md#存储与崩溃差异)、[操作日志差异](../DIFFERENCES.md#操作日志差异)，以及[映射](../mapping.md#minimongodb--mongodb-映射)中的 journal、checkpoint、recovery 行。

## 动手实验：撕裂最终帧

运行：

```bash
UV_CACHE_DIR=/tmp/minimongodb-uv-cache uv run python labs/lab_crash_recovery.py
```

实测输出：

```text
before injected crash: [{'_id': 1, 'state': 'checkpointed'}, {'_id': 2, 'state': 'torn-tail-write'}]
truncated journal tail; remaining bytes: 572
recovered documents: [{'_id': 1, 'state': 'checkpointed'}]
  The checkpoint survives; the incomplete final frame is discarded.
```

第一份文档位于 checkpoint。第二份原先在完整 frame 中，lab 故意删掉三字节；重启只接受有效前缀，并截断撕裂 frame。对当前 tagged codec，字节数是确定的。

该实验使用本地文件和 direct API，不验证 socket、replica set、write concern 或真实掉电。

## 练习

### 1. 理解题：为什么 journal 先于索引？

若集合先更新文档和索引，再 fsync `Journal.append`，会出现什么故障？

??? note "参考答案"

    append 失败可能留下内存可见但无持久记录的变更：调用者重启前观察到它，重启后却丢失。过早发布索引还会暴露与可恢复文档不一致的候选。journal-first 让易失状态成为持久接受的后果。

### 2. 理解题：尾部与中间损坏

为什么可以截断无效最终 frame，却必须对后面仍有字节的损坏 frame 报错？

??? note "参考答案"

    崩溃会自然中断当前 append，所以有效前缀后的无效 suffix 可修复。中间损坏会切断历史；保留后续 entry 而丢掉损坏前驱可能违反因果状态，系统无法安全推断后续字节仍是权威连续历史。

### 3. 动手题：验证 restart 不重新记日志

创建临时 `Database`，插入一份文档，记录 `journal.bin` 大小，重开两次并分别记录大小。验收：三个大小相同，每次重开都返回同一文档；不得修改 `src/`。

??? note "参考答案"

    使用 `TemporaryDirectory`、`Path(directory, "journal.bin").stat().st_size` 和三次 `Database(directory)` 构造。`_apply_oplog_entry` 不 emit 递归 oplog，因此 open 是 read/repair/replay，不是新写入。打印大小必须完全一致。

### 4. 动手题：提案 checkpoint checksum

起草但不应用检测 checkpoint 损坏的 diff 设计。验收：定义 framed format、checksum 覆盖范围、向后兼容选择、错误行为，以及 round trip、截断文件、翻转 payload 字节、原子替换测试。

??? note "参考答案"

    可接受设计可仿 journal，加入 magic/version header、payload length、tagged payload 和覆盖 payload 的 CRC32。`read_checkpoint` 必须在 decode 前校验所有部分并抛专用 corruption error，绝不能把已存在的损坏 checkpoint 静默视为空。测试应保留当前临时文件 fsync、`os.replace`、父目录 fsync 断言；提案必须说明拒绝还是迁移旧 unframed checkpoint。

## 小结

持久性是一条顺序合同。数据库集合共享一个 oplog，其 listener 在 sequence、文档和索引发布前追加并 fsync framed logical mutation。checkpoint 采用临时写、文件 fsync、原子 replace、目录 fsync。启动信任 CRC 有效 journal 前缀，只重放 snapshot 之后的 sequence。有了基础，第 6 章会研究相关但不同的性质：为什么持久帧中的逻辑更新可以安全重放多次。
