"""CRC journal framing, tail repair, and checkpoint snapshot contracts."""

import os
from pathlib import Path

import pytest

from minimongodb.oplog import OplogEntry
from minimongodb.storage import (
    Journal,
    JournalCorruptionError,
    read_checkpoint,
    write_checkpoint,
)


def _entry(sequence: int) -> OplogEntry:
    return OplogEntry(sequence, "items", "insert", sequence, {"_id": sequence})


def test_journal_round_trip_and_truncated_tail_repair(tmp_path: Path) -> None:
    path = tmp_path / "journal.bin"
    journal = Journal(path)
    journal.append(_entry(1))
    first_frame_size = path.stat().st_size
    journal.append(_entry(2))
    path.write_bytes(path.read_bytes()[:-3])

    assert journal.read_entries(repair=True) == [_entry(1)]
    assert path.stat().st_size == first_frame_size


def test_crc_failure_in_last_frame_is_repaired(tmp_path: Path) -> None:
    path = tmp_path / "journal.bin"
    journal = Journal(path)
    journal.append(_entry(1))
    data = bytearray(path.read_bytes())
    data[-1] ^= 0xFF
    path.write_bytes(data)
    assert journal.read_entries(repair=True) == []
    assert path.read_bytes() == b""


def test_crc_failure_before_a_later_frame_is_not_hidden(tmp_path: Path) -> None:
    path = tmp_path / "journal.bin"
    journal = Journal(path)
    journal.append(_entry(1))
    first_size = path.stat().st_size
    journal.append(_entry(2))
    data = bytearray(path.read_bytes())
    data[first_size - 1] ^= 0xFF
    path.write_bytes(data)
    with pytest.raises(JournalCorruptionError):
        journal.read_entries(repair=True)


def test_checkpoint_round_trips_tagged_object_ids(tmp_path: Path) -> None:
    from minimongodb import ObjectId

    path = tmp_path / "checkpoint.bin"
    state = {
        "sequence": 7,
        "collections": {"items": [{"_id": ObjectId(3), "nested": [1, True]}]},
    }
    write_checkpoint(path, state)
    assert read_checkpoint(path) == state


def test_checkpoint_fsyncs_parent_directory_after_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory_fd = 4242
    opened: list[tuple[Path, int]] = []
    fsynced: list[int] = []
    closed: list[int] = []

    def record_open(path, flags):
        opened.append((Path(path), flags))
        return directory_fd

    monkeypatch.setattr(os, "open", record_open)
    monkeypatch.setattr(os, "fsync", fsynced.append)
    monkeypatch.setattr(os, "close", closed.append)

    write_checkpoint(tmp_path / "checkpoint.bin", {"sequence": 0, "collections": {}})

    assert opened == [
        (
            tmp_path,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
    ]
    assert fsynced[-1] == directory_fd
    assert closed == [directory_fd]
