"""Checkpoint + valid journal prefix reconstructs deterministic state."""

from pathlib import Path

from minimongodb import Database
from minimongodb.oplog import OplogEntry
from minimongodb.storage import Journal


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
