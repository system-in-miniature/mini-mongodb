"""Append-only length/payload/CRC frames with conservative tail repair."""

from __future__ import annotations

import os
import struct
import zlib
from pathlib import Path

from minimongodb.errors import JournalCorruptionError
from minimongodb.oplog import OplogEntry
from minimongodb.storage.codec import decode_entry, encode_entry

_U32 = struct.Struct(">I")


class Journal:
    """Durable oplog frame stream; only an invalid final frame is repairable."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, entry: OplogEntry) -> None:
        payload = encode_entry(entry)
        frame = _U32.pack(len(payload)) + payload + _U32.pack(zlib.crc32(payload))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        previous_size = self.path.stat().st_size if self.path.exists() else 0
        try:
            with self.path.open("ab") as stream:
                written = stream.write(frame)
                if written != len(frame):
                    raise OSError(
                        f"short journal write: expected {len(frame)}, wrote {written}"
                    )
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            self._rollback_append(previous_size)
            raise

    def _rollback_append(self, previous_size: int) -> None:
        """Best-effort removal of bytes from an append that reported failure."""

        if not self.path.exists():
            return
        try:
            with self.path.open("r+b") as stream:
                stream.truncate(previous_size)
                stream.flush()
                os.fsync(stream.fileno())
        except OSError:
            # Preserve the original append error; restart tail repair remains
            # the final defense if the cleanup fsync also fails.
            pass

    def read_entries(self, *, repair: bool = True) -> list[OplogEntry]:
        if not self.path.exists():
            return []
        data = self.path.read_bytes()
        entries: list[OplogEntry] = []
        offset = 0
        while offset < len(data):
            frame_start = offset
            if len(data) - offset < _U32.size:
                return self._repair_or_raise(entries, frame_start, repair)
            (payload_size,) = _U32.unpack_from(data, offset)
            offset += _U32.size
            frame_end = offset + payload_size + _U32.size
            if frame_end > len(data):
                return self._repair_or_raise(entries, frame_start, repair)
            payload = data[offset : offset + payload_size]
            offset += payload_size
            (stored_crc,) = _U32.unpack_from(data, offset)
            offset += _U32.size
            if zlib.crc32(payload) != stored_crc:
                if frame_end < len(data):
                    raise JournalCorruptionError(
                        f"CRC mismatch before journal tail at byte {frame_start}"
                    )
                return self._repair_or_raise(entries, frame_start, repair)
            try:
                entries.append(decode_entry(payload))
            except (KeyError, TypeError, ValueError) as error:
                if frame_end < len(data):
                    raise JournalCorruptionError(
                        f"invalid frame before journal tail at byte {frame_start}"
                    ) from error
                return self._repair_or_raise(entries, frame_start, repair)
        return entries

    def _repair_or_raise(
        self, entries: list[OplogEntry], valid_size: int, repair: bool
    ) -> list[OplogEntry]:
        if not repair:
            raise JournalCorruptionError(f"invalid journal tail at byte {valid_size}")
        # The valid prefix is authoritative; a crash may leave any suffix.
        with self.path.open("r+b") as stream:
            stream.truncate(valid_size)
            stream.flush()
            os.fsync(stream.fileno())
        return entries
