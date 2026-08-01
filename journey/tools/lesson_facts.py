"""Reviewed bilingual mechanism facts for the nine MiniMongoDB Stages."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LessonFacts:
    title_en: str
    title_zh: str
    problem_en: str
    problem_zh: str
    failure_en: str
    failure_zh: str
    concepts_en: str
    concepts_zh: str
    runtime_en: str
    runtime_zh: str
    statement_en: str
    statement_zh: str


FACTS = (
    LessonFacts(
        "BSON values and dotted paths",
        "BSON 值与点路径",
        "A document store cannot compare, copy, identify, or traverse arbitrary Python values without a closed value contract.",
        "文档存储若没有封闭的值契约，就无法可靠比较、复制、标识或遍历任意 Python 值。",
        "The tests use nested aliases, unsupported values, ordered documents, mixed numeric identities, and invalid list paths to expose accidental Python semantics.",
        "测试用嵌套别名、不支持的值、有序文档、混合数值身份与非法数组路径，暴露偶然的 Python 语义。",
        "MiniMongoDB's BSON subset defines owned document copies, explicit type tags, exact equality, total ordering, ObjectId generation, and dotted reads or writes.",
        "MiniMongoDB 的 BSON 子集定义受控文档副本、显式类型标签、精确相等、全序、ObjectId 生成和点路径读写。",
        "Values are validated and copied at the boundary; path traversal then walks mappings and numeric list positions without leaking caller-owned state.",
        "值在边界被校验和复制；随后路径遍历只沿 Mapping 与数字数组下标前进，不泄漏调用方状态。",
        "Canonical value semantics must precede indexes, matching, logging, and persistence because all four reuse the same notion of identity.",
        "规范值语义必须先于索引、匹配、日志和持久化，因为四者复用同一套身份定义。",
    ),
    LessonFacts(
        "Array-aware query matching",
        "数组感知的查询匹配",
        "Dotted paths and arrays make a query document ambiguous unless scalar element matching and exact compound-value equality are separated.",
        "点路径与数组会让查询文档产生歧义，必须区分标量逐元素匹配与复合值精确相等。",
        "The counterexamples compare scalar-to-array matching, literal array order, exact embedded documents, dotted traversal, logical branches, and unknown operators.",
        "反例比较标量对数组匹配、字面数组顺序、嵌入文档精确匹配、点路径展开、逻辑分支与未知算子。",
        "A query is a recursive predicate tree. Field resolution may fan out through arrays, while a literal list or document remains one exact BSON value.",
        "查询是递归谓词树。字段解析可以穿过数组展开，而字面 List 或 Document 仍是一个精确 BSON 值。",
        "The matcher resolves candidate values, applies field operators to them, and combines logical clauses without mutating the document.",
        "Matcher 解析候选值、对它们应用字段算子，再组合逻辑子句，全程不修改文档。",
        "Keeping traversal and equality distinct prevents a partial embedded document from silently behaving like a dotted-field query.",
        "把遍历与相等分开，可防止部分嵌入文档悄悄变成点字段查询。",
    ),
    LessonFacts(
        "Durable oplog frames",
        "持久化 Oplog 帧",
        "In-memory operations are not restartable until entries, bytes, frame boundaries, corruption handling, and checkpoint replacement are explicit.",
        "内存操作只有在 Entry、字节、帧边界、损坏处理和 Checkpoint 替换都明确后，才能支持重启。",
        "Tests truncate the final frame, corrupt its CRC or an earlier frame, round-trip tagged values, and inspect atomic checkpoint replacement.",
        "测试截断末尾帧、破坏末帧或中间帧 CRC、往返带标签值，并检查 Checkpoint 原子替换。",
        "An oplog entry is a deterministic state transition record; the codec makes values self-describing, the journal frames entries with length and CRC, and a checkpoint snapshots a prefix.",
        "Oplog Entry 是确定性状态转换记录；Codec 让值自描述，Journal 用长度和 CRC 组帧，Checkpoint 快照化一个前缀。",
        "Append encodes and fsyncs one frame. Recovery accepts complete frames, may trim only a damaged final tail, and combines them with the latest atomic checkpoint.",
        "Append 编码并 Fsync 一个帧。恢复接受完整帧，只能裁掉损坏的最终尾部，并与最新原子 Checkpoint 合并。",
        "Only the final incomplete frame is repairable; hiding corruption before later bytes would invent a history that was never durably ordered.",
        "只有最终不完整帧可修复；隐藏后面仍有字节的中间损坏，会虚构一段从未持久排序的历史。",
    ),
    LessonFacts(
        "CRUD, updates, and recovery",
        "CRUD、更新与恢复闭环",
        "Value and storage primitives do not yet form a database: one owner must coordinate identity, matching, mutation, oplog post-images, checkpoints, and startup replay.",
        "值与存储原语还不是数据库：必须由一个所有者协调身份、匹配、修改、Oplog 后镜像、Checkpoint 与启动回放。",
        "The suite probes duplicate and immutable ids, partial batches, copied results, dotted update operators, idempotent replay, and checkpoint-plus-journal restart.",
        "测试覆盖重复与不可变 `_id`、部分批次、返回值副本、点路径更新算子、幂等回放及 Checkpoint 加 Journal 重启。",
        "Collection owns live documents and indexes; Database owns named collections and durability. Operator updates become final-state post-images before logging.",
        "Collection 拥有活文档与索引；Database 拥有命名集合与持久性。算子更新在写日志前变成最终状态后镜像。",
        "A write validates a candidate, allocates its sequence, records the durable transition, then publishes owned state. Startup loads a checkpoint and replays only newer entries.",
        "写入先校验候选状态、分配序号、记录持久转换，再发布受控状态。启动时载入 Checkpoint，只回放更新的 Entry。",
        "Logging final assignments rather than user commands makes replay idempotent and keeps repeated recovery from applying `$inc` twice.",
        "记录最终赋值而非用户命令，使回放幂等，并避免重复恢复把 `$inc` 执行两次。",
    ),
    LessonFacts(
        "Journal-first identity boundary",
        "日志优先与身份边界",
        "The first implementation exposed three crash edges: publishing before journal success, using non-canonical `_id` keys, and renaming a checkpoint without syncing its directory.",
        "第一版暴露三个崩溃边界：Journal 成功前发布、使用非规范 `_id` Key，以及替换 Checkpoint 后未同步目录。",
        "Failure injection interrupts open, write, and fsync for insert, update, and delete; identity cases compare bool, numbers, NaN, and nested BSON; filesystem spies require directory fsync.",
        "故障注入在 Insert、Update、Delete 的 Open、Write、Fsync 处中断；身份用例比较 Bool、Number、NaN 与嵌套 BSON；文件系统探针要求目录 Fsync。",
        "Journal-first means the durable append is the commit point for each logical write. Canonical keys make index identity agree with BSON equality, and directory fsync makes rename durable.",
        "Journal-first 表示持久 Append 是每次逻辑写的提交点。Canonical Key 让索引身份与 BSON 相等一致，目录 Fsync 让 Rename 真正持久。",
        "The collection prepares new state without exposing it, appends and syncs the oplog entry, then mutates documents and indexes; failure leaves the prior visible state.",
        "Collection 先准备但不暴露新状态，Append 并同步 Oplog Entry，最后修改文档与索引；失败时保留旧可见状态。",
        "Ordering is the proof: moving publication before append can acknowledge state that restart cannot reconstruct.",
        "顺序本身就是证明：若把发布移到 Append 前，就可能确认一份重启无法重建的状态。",
    ),
    LessonFacts(
        "Indexed plans and aggregation pipelines",
        "索引计划与聚合管道",
        "The M2 collection needs reusable access paths and staged document transformation, but both must preserve the same BSON and ownership semantics as a collection scan.",
        "M2 Collection 需要可复用访问路径与分阶段文档变换，但两者都必须保持与 Collection Scan 相同的 BSON 与所有权语义。",
        "Tests combine multikey and compound indexes, selectivity and explain counters, plus match, project, group, BSON-aware sort, limit, and malformed pipeline stages.",
        "测试组合 Multikey 与 Compound Index、选择度与 Explain 计数，以及 Match、Project、Group、BSON 感知 Sort、Limit 和错误 Pipeline Stage。",
        "Indexes map canonical keys to candidates, plans choose COLLSCAN or IXSCAN explicitly, and an aggregation pipeline composes ordered streaming or blocking document operators.",
        "索引把 Canonical Key 映射到 Candidate，Plan 显式选择 COLLSCAN 或 IXSCAN，Aggregation Pipeline 则组合有序的流式或阻塞文档算子。",
        "Writes stage all index entries before publication; reads fetch and recheck planned candidates; aggregation then threads owned documents through each validated stage.",
        "写入在发布前暂存全部索引项；读取取回并重检计划候选；随后聚合把受控文档依次传过每个已校验 Stage。",
        "Access paths never replace predicate rechecking, and pipeline order remains observable; these boundaries keep optimization from changing document semantics.",
        "访问路径不能取代谓词重检，Pipeline 顺序也必须可观察；这些边界防止优化改变文档语义。",
    ),
    LessonFacts(
        "Query validation before planning",
        "规划前的查询校验",
        "When validation occurs only while matching documents, an invalid query can appear valid on an empty collection or an index path with no candidate.",
        "若只在匹配文档时校验，非法查询会在空集合或无候选索引路径上看似合法。",
        "The regression asks both `find` and `explain` to execute a malformed `$in` against an empty collection and nests another malformed operand behind a logical branch.",
        "回归测试让 `find` 与 `explain` 在空集合上执行错误 `$in`，并把另一错误操作数藏在逻辑分支后。",
        "Syntax validity is an input property, independent of data cardinality or the chosen access path. Validation therefore walks the complete query tree before planning.",
        "语法有效性是输入属性，与数据量和访问路径无关，因此校验必须在规划前遍历完整查询树。",
        "Collection validates once at the public boundary; matcher can then evaluate candidates under the same recursively checked operator contract.",
        "Collection 在公共边界统一校验；Matcher 随后按同一套递归检查过的算子契约评估候选。",
        "Moving validation ahead of plan selection makes the same malformed query fail for empty, scanned, and indexed collections.",
        "把校验移到选计划之前，可让同一非法查询在空集合、扫描与索引集合上都一致失败。",
    ),
    LessonFacts(
        "Executable domain experiments",
        "可执行领域实验",
        "Individual unit contracts do not show whether the public API can demonstrate the complete document-database mechanisms as runnable experiments.",
        "单个单元契约无法说明公共 API 是否能把完整文档数据库机制展示成可运行实验。",
        "The lab contract starts each script in a fresh process and checks visible markers for array semantics, idempotence, crash recovery, multikey expansion, and plan changes.",
        "Lab 契约在新进程中启动每个脚本，并检查数组语义、幂等、崩溃恢复、多键展开与计划变化的可见标记。",
        "A lab is a small end-to-end observation surface built only from exported APIs; it connects internal invariants to behavior a learner can reproduce.",
        "Lab 是只使用导出 API 的小型端到端观察面，把内部不变量连接到学习者可复现的行为。",
        "Each process constructs one counterexample, prints the important before-and-after state, and exits without relying on private fixtures or prior data.",
        "每个进程构造一个反例、打印关键前后状态，并且不依赖私有 Fixture 或已有数据即可退出。",
        "Fresh-process execution closes the domain loop: imports, public ownership, persistence, and observable terminology must work together.",
        "新进程执行闭合领域回路：导入、公共所有权、持久化与可观察术语必须协同工作。",
    ),
)
