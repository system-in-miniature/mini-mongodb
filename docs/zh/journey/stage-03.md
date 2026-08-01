# Stage 03 · 持久化 Oplog 帧

### 目标

实现持久化 Oplog 帧，并能从可执行反例、运行时状态与关键语句解释其边界。

??? note "交付文件"
    - `src/minimongodb/oplog/__init__.py`
    - `src/minimongodb/oplog/capped.py`
    - `src/minimongodb/oplog/entry.py`
    - `src/minimongodb/storage/__init__.py`
    - `src/minimongodb/storage/checkpoint.py`
    - `src/minimongodb/storage/codec.py`
    - `src/minimongodb/storage/journal.py`
    - `src/minimongodb/storage/recovery.py`
    - `tests/test_storage.py`

### 当前遇到的问题

内存操作只有在 Entry、字节、帧边界、损坏处理和 Checkpoint 替换都明确后，才能支持重启。

### 测试契约

#### 先看会坏在哪里

测试截断末尾帧、破坏末帧或中间帧 CRC、往返带标签值，并检查 Checkpoint 原子替换。

??? note "文件差异：tests/test_storage.py"
    ```diff
    diff --git a/tests/test_storage.py b/tests/test_storage.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..3c63148b6b2c94d4156021490f0f37b31c1e1380
    --- /dev/null
    +++ b/tests/test_storage.py
    @@ -0,0 +1,65 @@
    +"""CRC journal framing, tail repair, and checkpoint snapshot contracts."""
    +
    +from pathlib import Path
    +
    +import pytest
    +
    +from minimongodb.oplog import OplogEntry
    +from minimongodb.storage import (
    +    Journal,
    +    JournalCorruptionError,
    +    read_checkpoint,
    +    write_checkpoint,
    +)
    +
    +
    +def _entry(sequence: int) -> OplogEntry:
    +    return OplogEntry(sequence, "items", "insert", sequence, {"_id": sequence})
    +
    +
    +def test_journal_round_trip_and_truncated_tail_repair(tmp_path: Path) -> None:
    +    path = tmp_path / "journal.bin"
    +    journal = Journal(path)
    +    journal.append(_entry(1))
    +    first_frame_size = path.stat().st_size
    +    journal.append(_entry(2))
    +    path.write_bytes(path.read_bytes()[:-3])
    +
    +    assert journal.read_entries(repair=True) == [_entry(1)]
    +    assert path.stat().st_size == first_frame_size
    +
    +
    +def test_crc_failure_in_last_frame_is_repaired(tmp_path: Path) -> None:
    +    path = tmp_path / "journal.bin"
    +    journal = Journal(path)
    +    journal.append(_entry(1))
    +    data = bytearray(path.read_bytes())
    +    data[-1] ^= 0xFF
    +    path.write_bytes(data)
    +    assert journal.read_entries(repair=True) == []
    +    assert path.read_bytes() == b""
    +
    +
    +def test_crc_failure_before_a_later_frame_is_not_hidden(tmp_path: Path) -> None:
    +    path = tmp_path / "journal.bin"
    +    journal = Journal(path)
    +    journal.append(_entry(1))
    +    first_size = path.stat().st_size
    +    journal.append(_entry(2))
    +    data = bytearray(path.read_bytes())
    +    data[first_size - 1] ^= 0xFF
    +    path.write_bytes(data)
    +    with pytest.raises(JournalCorruptionError):
    +        journal.read_entries(repair=True)
    +
    +
    +def test_checkpoint_round_trips_tagged_object_ids(tmp_path: Path) -> None:
    +    from minimongodb import ObjectId
    +
    +    path = tmp_path / "checkpoint.bin"
    +    state = {
    +        "sequence": 7,
    +        "collections": {"items": [{"_id": ObjectId(3), "nested": [1, True]}]},
    +    }
    +    write_checkpoint(path, state)
    +    assert read_checkpoint(path) == state
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

测试截断末尾帧、破坏末帧或中间帧 CRC、往返带标签值，并检查 Checkpoint 原子替换。

**关键测试语句**

```python
assert journal.read_entries(repair=True) == [_entry(1)]
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

Oplog Entry 是确定性状态转换记录；Codec 让值自描述，Journal 用长度和 CRC 组帧，Checkpoint 快照化一个前缀。

### 为什么需要这个机制

内存操作只有在 Entry、字节、帧边界、损坏处理和 Checkpoint 替换都明确后，才能支持重启。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Append 编码并 Fsync 一个帧。恢复接受完整帧，只能裁掉损坏的最终尾部，并与最新原子 Checkpoint 合并。

### 机制板块

#### 持久化 Oplog 帧机制

Append 编码并 Fsync 一个帧。恢复接受完整帧，只能裁掉损坏的最终尾部，并与最新原子 Checkpoint 合并。

??? note "文件差异：src/minimongodb/oplog/capped.py"
    ```diff
    diff --git a/src/minimongodb/oplog/capped.py b/src/minimongodb/oplog/capped.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..031516733bb855b11ffda01fb7e07c413d5ed167
    --- /dev/null
    +++ b/src/minimongodb/oplog/capped.py
    @@ -0,0 +1,6 @@
    +"""M3 placeholder for capped oplog retention.
    +
    +M1 intentionally keeps an unbounded in-memory sequence plus durable journal.
    +M3 will replace the backing list with a bounded ring while preserving the
    +``OplogEntry`` and replay contracts.  No fake capped behavior is exposed here.
    +"""
    ```

??? note "文件差异：src/minimongodb/oplog/entry.py"
    ```diff
    diff --git a/src/minimongodb/oplog/entry.py b/src/minimongodb/oplog/entry.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..69eb2f6e91ee89ff55fb356c66979a3c77bfedba
    --- /dev/null
    +++ b/src/minimongodb/oplog/entry.py
    @@ -0,0 +1,69 @@
    +"""Deterministic oplog entry model.
    +
    +User updates describe an action (for example, "increment by three").  Oplog
    +updates instead describe the resulting assignment ("set count to five").
    +Repeating an action changes state twice; repeating an assignment converges on
    +the same state.  That is why collection integration rewrites every modified
    +path to its post-image.
    +"""
    +
    +from __future__ import annotations
    +
    +from collections.abc import Callable, Iterator
    +from dataclasses import dataclass
    +from typing import Any
    +
    +from minimongodb.bson import clone_document
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class OplogEntry:
    +    """One post-image-oriented mutation in a named collection."""
    +
    +    sequence: int
    +    collection: str
    +    operation: str
    +    key: Any
    +    payload: dict[str, Any] | None = None
    +
    +
    +class Oplog:
    +    """Append-only v1 log; bounded/capped retention is deliberately M3."""
    +
    +    def __init__(
    +        self,
    +        *,
    +        start_sequence: int = 1,
    +        listener: Callable[[OplogEntry], None] | None = None,
    +    ) -> None:
    +        self._entries: list[OplogEntry] = []
    +        self._next_sequence = start_sequence
    +        self._listener = listener
    +
    +    def __iter__(self) -> Iterator[OplogEntry]:
    +        return iter(self._entries)
    +
    +    @property
    +    def last_sequence(self) -> int:
    +        return self._next_sequence - 1
    +
    +    def emit(
    +        self,
    +        collection: str,
    +        operation: str,
    +        key: Any,
    +        payload: dict[str, Any] | None = None,
    +    ) -> OplogEntry:
    +        entry = OplogEntry(
    +            sequence=self._next_sequence,
    +            collection=collection,
    +            operation=operation,
    +            key=key,
    +            payload=clone_document(payload) if payload is not None else None,
    +        )
    +        self._next_sequence += 1
    +        self._entries.append(entry)
    +        if self._listener is not None:
    +            # Persistence observes only complete in-memory mutations.
    +            self._listener(entry)
    +        return entry
    ```

??? note "文件差异：src/minimongodb/storage/checkpoint.py"
    ```diff
    diff --git a/src/minimongodb/storage/checkpoint.py b/src/minimongodb/storage/checkpoint.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..ed2a791950bf5d3bc7801342cc2903baad8dce48
    --- /dev/null
    +++ b/src/minimongodb/storage/checkpoint.py
    @@ -0,0 +1,31 @@
    +"""Atomic whole-database snapshots for the single-writer teaching engine."""
    +
    +from __future__ import annotations
    +
    +import os
    +from pathlib import Path
    +from typing import Any
    +
    +from minimongodb.storage.codec import decode_value, encode_value
    +
    +
    +def write_checkpoint(path: str | Path, state: dict[str, Any]) -> None:
    +    destination = Path(path)
    +    destination.parent.mkdir(parents=True, exist_ok=True)
    +    temporary = destination.with_suffix(destination.suffix + ".tmp")
    +    payload = encode_value(state)
    +    with temporary.open("wb") as stream:
    +        stream.write(payload)
    +        stream.flush()
    +        os.fsync(stream.fileno())
    +    os.replace(temporary, destination)
    +
    +
    +def read_checkpoint(path: str | Path) -> dict[str, Any] | None:
    +    source = Path(path)
    +    if not source.exists():
    +        return None
    +    value = decode_value(source.read_bytes())
    +    if not isinstance(value, dict):
    +        raise ValueError("checkpoint root must be a document")
    +    return value
    ```

??? note "文件差异：src/minimongodb/storage/codec.py"
    ```diff
    diff --git a/src/minimongodb/storage/codec.py b/src/minimongodb/storage/codec.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..c27f446ff3eab186e118782b7dec99b0b9a32d69
    --- /dev/null
    +++ b/src/minimongodb/storage/codec.py
    @@ -0,0 +1,76 @@
    +"""Deterministic tagged JSON codec for the supported BSON teaching subset.
    +
    +Using tagged nodes avoids silently turning an ``ObjectId`` into a string or a
    +boolean into a number.  Real MongoDB writes binary BSON/WiredTiger pages; JSON
    +here is an inspectable serialization detail, not a claim of wire compatibility.
    +"""
    +
    +from __future__ import annotations
    +
    +import json
    +from typing import Any
    +
    +from minimongodb.bson import ObjectId, type_tag
    +from minimongodb.oplog import OplogEntry
    +
    +
    +def _to_node(value: Any) -> dict[str, Any]:
    +    tag = type_tag(value)
    +    if tag == "document":
    +        return {"t": "document", "v": [[key, _to_node(item)] for key, item in value.items()]}
    +    if tag == "array":
    +        return {"t": "array", "v": [_to_node(item) for item in value]}
    +    if tag == "objectId":
    +        return {"t": "objectId", "v": value.value}
    +    return {"t": tag, "v": value}
    +
    +
    +def _from_node(node: dict[str, Any]) -> Any:
    +    tag = node["t"]
    +    value = node["v"]
    +    if tag == "document":
    +        return {key: _from_node(item) for key, item in value}
    +    if tag == "array":
    +        return [_from_node(item) for item in value]
    +    if tag == "objectId":
    +        return ObjectId(value)
    +    if tag in {"null", "number", "string", "bool"}:
    +        return value
    +    raise ValueError(f"unknown encoded type tag: {tag!r}")
    +
    +
    +def encode_value(value: Any) -> bytes:
    +    """Encode one supported value with stable separators and key ordering."""
    +
    +    return json.dumps(
    +        _to_node(value),
    +        ensure_ascii=False,
    +        separators=(",", ":"),
    +    ).encode("utf-8")
    +
    +
    +def decode_value(payload: bytes) -> Any:
    +    return _from_node(json.loads(payload.decode("utf-8")))
    +
    +
    +def encode_entry(entry: OplogEntry) -> bytes:
    +    return encode_value(
    +        {
    +            "sequence": entry.sequence,
    +            "collection": entry.collection,
    +            "operation": entry.operation,
    +            "key": entry.key,
    +            "payload": entry.payload,
    +        }
    +    )
    +
    +
    +def decode_entry(payload: bytes) -> OplogEntry:
    +    value = decode_value(payload)
    +    return OplogEntry(
    +        value["sequence"],
    +        value["collection"],
    +        value["operation"],
    +        value["key"],
    +        value["payload"],
    +    )
    ```

??? note "文件差异：src/minimongodb/storage/journal.py"
    ```diff
    diff --git a/src/minimongodb/storage/journal.py b/src/minimongodb/storage/journal.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..142911435cc0ed6269cba8860c487037825a2bcf
    --- /dev/null
    +++ b/src/minimongodb/storage/journal.py
    @@ -0,0 +1,77 @@
    +"""Append-only length/payload/CRC frames with conservative tail repair."""
    +
    +from __future__ import annotations
    +
    +import os
    +import struct
    +import zlib
    +from pathlib import Path
    +
    +from minimongodb.errors import JournalCorruptionError
    +from minimongodb.oplog import OplogEntry
    +from minimongodb.storage.codec import decode_entry, encode_entry
    +
    +_U32 = struct.Struct(">I")
    +
    +
    +class Journal:
    +    """Durable oplog frame stream; only an invalid final frame is repairable."""
    +
    +    def __init__(self, path: str | Path) -> None:
    +        self.path = Path(path)
    +
    +    def append(self, entry: OplogEntry) -> None:
    +        payload = encode_entry(entry)
    +        frame = _U32.pack(len(payload)) + payload + _U32.pack(zlib.crc32(payload))
    +        self.path.parent.mkdir(parents=True, exist_ok=True)
    +        with self.path.open("ab") as stream:
    +            stream.write(frame)
    +            stream.flush()
    +            os.fsync(stream.fileno())
    +
    +    def read_entries(self, *, repair: bool = True) -> list[OplogEntry]:
    +        if not self.path.exists():
    +            return []
    +        data = self.path.read_bytes()
    +        entries: list[OplogEntry] = []
    +        offset = 0
    +        while offset < len(data):
    +            frame_start = offset
    +            if len(data) - offset < _U32.size:
    +                return self._repair_or_raise(entries, frame_start, repair)
    +            (payload_size,) = _U32.unpack_from(data, offset)
    +            offset += _U32.size
    +            frame_end = offset + payload_size + _U32.size
    +            if frame_end > len(data):
    +                return self._repair_or_raise(entries, frame_start, repair)
    +            payload = data[offset : offset + payload_size]
    +            offset += payload_size
    +            (stored_crc,) = _U32.unpack_from(data, offset)
    +            offset += _U32.size
    +            if zlib.crc32(payload) != stored_crc:
    +                if frame_end < len(data):
    +                    raise JournalCorruptionError(
    +                        f"CRC mismatch before journal tail at byte {frame_start}"
    +                    )
    +                return self._repair_or_raise(entries, frame_start, repair)
    +            try:
    +                entries.append(decode_entry(payload))
    +            except (KeyError, TypeError, ValueError) as error:
    +                if frame_end < len(data):
    +                    raise JournalCorruptionError(
    +                        f"invalid frame before journal tail at byte {frame_start}"
    +                    ) from error
    +                return self._repair_or_raise(entries, frame_start, repair)
    +        return entries
    +
    +    def _repair_or_raise(
    +        self, entries: list[OplogEntry], valid_size: int, repair: bool
    +    ) -> list[OplogEntry]:
    +        if not repair:
    +            raise JournalCorruptionError(f"invalid journal tail at byte {valid_size}")
    +        # The valid prefix is authoritative; a crash may leave any suffix.
    +        with self.path.open("r+b") as stream:
    +            stream.truncate(valid_size)
    +            stream.flush()
    +            os.fsync(stream.fileno())
    +        return entries
    ```

??? note "文件差异：src/minimongodb/storage/recovery.py"
    ```diff
    diff --git a/src/minimongodb/storage/recovery.py b/src/minimongodb/storage/recovery.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..27b52dea82fdc285a5905a16f9b4c7222f12aca9
    --- /dev/null
    +++ b/src/minimongodb/storage/recovery.py
    @@ -0,0 +1,33 @@
    +"""Load the checkpoint and repaired valid journal prefix as recovery inputs."""
    +
    +from __future__ import annotations
    +
    +from dataclasses import dataclass
    +from pathlib import Path
    +from typing import Any
    +
    +from minimongodb.oplog import OplogEntry
    +from minimongodb.storage.checkpoint import read_checkpoint
    +from minimongodb.storage.journal import Journal
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class RecoveryState:
    +    checkpoint_sequence: int
    +    collections: dict[str, list[dict[str, Any]]]
    +    journal_entries: list[OplogEntry]
    +
    +
    +def load_recovery_state(directory: str | Path) -> RecoveryState:
    +    """Read durable inputs without applying them or producing new writes."""
    +
    +    root = Path(directory)
    +    checkpoint = read_checkpoint(root / "checkpoint.bin") or {
    +        "sequence": 0,
    +        "collections": {},
    +    }
    +    return RecoveryState(
    +        checkpoint_sequence=checkpoint["sequence"],
    +        collections=checkpoint["collections"],
    +        journal_entries=Journal(root / "journal.bin").read_entries(repair=True),
    +    )
    ```

**是什么，为什么现在需要**

Oplog Entry 是确定性状态转换记录；Codec 让值自描述，Journal 用长度和 CRC 组帧，Checkpoint 快照化一个前缀。

**在运行时做什么**

Append 编码并 Fsync 一个帧。恢复接受完整帧，只能裁掉损坏的最终尾部，并与最新原子 Checkpoint 合并。

**关键语句理解**

只有最终不完整帧可修复；隐藏后面仍有字节的中间损坏，会虚构一段从未持久排序的历史。

#### 包、Fixture 与工程支撑

保持包导出、测试语料、依赖与运行环境可复现。

??? note "支撑文件差异（2 个文件）"
    **`src/minimongodb/oplog/__init__.py`**

    ```diff
    diff --git a/src/minimongodb/oplog/__init__.py b/src/minimongodb/oplog/__init__.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..1e82bea70e95cb5fc2d1a57292b4497ed8e75cfc
    --- /dev/null
    +++ b/src/minimongodb/oplog/__init__.py
    @@ -0,0 +1,13 @@
    +"""Logical write log whose entries can safely be replayed more than once."""
    +
    +from minimongodb.oplog.entry import Oplog, OplogEntry
    +
    +
    +def replay(*args, **kwargs):
    +    """Import the collection-aware replayer lazily to avoid an API cycle."""
    +
    +    from minimongodb.oplog.replay import replay as replay_entries
    +
    +    return replay_entries(*args, **kwargs)
    +
    +__all__ = ["Oplog", "OplogEntry", "replay"]
    ```

    **`src/minimongodb/storage/__init__.py`**

    ```diff
    diff --git a/src/minimongodb/storage/__init__.py b/src/minimongodb/storage/__init__.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..d76e8665db62a0c9080f2018749f55862b2550b5
    --- /dev/null
    +++ b/src/minimongodb/storage/__init__.py
    @@ -0,0 +1,15 @@
    +"""Durability primitives: tagged codec, CRC journal, checkpoint, recovery."""
    +
    +from minimongodb.errors import JournalCorruptionError
    +from minimongodb.storage.checkpoint import read_checkpoint, write_checkpoint
    +from minimongodb.storage.journal import Journal
    +from minimongodb.storage.recovery import RecoveryState, load_recovery_state
    +
    +__all__ = [
    +    "Journal",
    +    "JournalCorruptionError",
    +    "RecoveryState",
    +    "load_recovery_state",
    +    "read_checkpoint",
    +    "write_checkpoint",
    +]
    ```


### 验证证据

运行 `uv run pytest -q $(cat journey/stages/03-durable-log-frames/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

只有最终不完整帧可修复；隐藏后面仍有字节的中间损坏，会虚构一段从未持久排序的历史。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 5 章](https://github.com/system-in-miniature/mini-mongodb/blob/main/docs/zh/tutorial/05-durability.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-mongodb/blob/main/journey/stages/03-durable-log-frames/stage.patch)
