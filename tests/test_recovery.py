"""Checkpoint + valid journal prefix reconstructs deterministic state."""

from pathlib import Path

import pytest

from minimongodb import Database
from minimongodb.oplog import OplogEntry
from minimongodb.storage import Journal
from minimongodb.storage import journal as journal_module


def test_restart_uses_checkpoint_then_only_newer_journal_entries(tmp_path: Path) -> None:
    database = Database(tmp_path)
    items = database.get_collection("items")
    items.insert_one({"_id": 1, "value": "checkpoint"})
    database.checkpoint()
    items.insert_one({"_id": 2, "value": "journal"})

    recovered = Database(tmp_path)
    assert recovered.get_collection("items").find() == [
        {"_id": 1, "value": "checkpoint"},
        {"_id": 2, "value": "journal"},
    ]
    # Starting yet again proves startup replay itself did not append records.
    assert Database(tmp_path).get_collection("items").find() == recovered.get_collection(
        "items"
    ).find()


def test_every_incomplete_second_frame_recovers_the_complete_prefix(
    tmp_path: Path,
) -> None:
    template = tmp_path / "template.bin"
    journal = Journal(template)
    journal.append(OplogEntry(1, "items", "insert", 1, {"_id": 1}))
    first_size = template.stat().st_size
    journal.append(OplogEntry(2, "items", "insert", 2, {"_id": 2}))
    complete = template.read_bytes()

    for cut in range(first_size, len(complete)):
        case = tmp_path / f"cut-{cut}"
        case.mkdir()
        (case / "journal.bin").write_bytes(complete[:cut])
        recovered = Database(case)
        assert recovered.get_collection("items").find() == [{"_id": 1}]


class _WriteFailingStream:
    def __init__(self, stream) -> None:
        self._stream = stream

    def __enter__(self):
        self._stream.__enter__()
        return self

    def __exit__(self, *args):
        return self._stream.__exit__(*args)

    def write(self, data: bytes) -> int:
        self._stream.write(data[: len(data) // 2])
        self._stream.flush()
        raise OSError("injected journal write failure")

    def __getattr__(self, name):
        return getattr(self._stream, name)


@pytest.mark.parametrize("failure_stage", ["open", "write", "fsync"])
@pytest.mark.parametrize("operation", ["insert", "update", "delete"])
def test_failed_journal_append_is_not_published_or_replayed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
    operation: str,
) -> None:
    database = Database(tmp_path)
    items = database["items"]
    items.insert_one({"_id": 1, "state": "durable"})
    journal_path = tmp_path / "journal.bin"
    original_open = Path.open
    original_fsync = journal_module.os.fsync

    with monkeypatch.context() as injected:
        if failure_stage == "open":

            def failing_open(path, mode="r", *args, **kwargs):
                if path == journal_path and mode == "ab":
                    raise OSError("injected journal open failure")
                return original_open(path, mode, *args, **kwargs)

            injected.setattr(Path, "open", failing_open)
        elif failure_stage == "write":

            def write_failing_open(path, mode="r", *args, **kwargs):
                stream = original_open(path, mode, *args, **kwargs)
                if path == journal_path and mode == "ab":
                    return _WriteFailingStream(stream)
                return stream

            injected.setattr(Path, "open", write_failing_open)
        else:
            failed = False

            def failing_fsync(fd: int) -> None:
                nonlocal failed
                if not failed:
                    failed = True
                    raise OSError("injected journal fsync failure")
                original_fsync(fd)

            injected.setattr(journal_module.os, "fsync", failing_fsync)

        with pytest.raises(OSError, match=f"injected journal {failure_stage} failure"):
            if operation == "insert":
                items.insert_one({"_id": 2, "state": "must stay invisible"})
            elif operation == "update":
                items.update_one(
                    {"_id": 1},
                    {"$set": {"state": "must stay invisible"}},
                )
            else:
                items.delete_one({"_id": 1})

    assert items.find() == [{"_id": 1, "state": "durable"}]
    assert [entry.sequence for entry in database.oplog] == [1]
    assert database.oplog.last_sequence == 1

    failed_restart = Database(tmp_path)
    assert failed_restart["items"].find() == [{"_id": 1, "state": "durable"}]
    assert failed_restart.oplog.last_sequence == 1

    if operation == "insert":
        items.insert_one({"_id": 2, "state": "retry"})
        expected = [
            {"_id": 1, "state": "durable"},
            {"_id": 2, "state": "retry"},
        ]
    elif operation == "update":
        items.update_one({"_id": 1}, {"$set": {"state": "retry"}})
        expected = [{"_id": 1, "state": "retry"}]
    else:
        items.delete_one({"_id": 1})
        expected = []
    assert [entry.sequence for entry in database.oplog] == [1, 2]
    assert Database(tmp_path)["items"].find() == expected
