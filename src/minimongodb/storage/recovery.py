"""Load the checkpoint and repaired valid journal prefix as recovery inputs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from minimongodb.oplog import OplogEntry
from minimongodb.storage.checkpoint import read_checkpoint
from minimongodb.storage.journal import Journal


@dataclass(frozen=True, slots=True)
class RecoveryState:
    checkpoint_sequence: int
    collections: dict[str, list[dict[str, Any]]]
    journal_entries: list[OplogEntry]


def load_recovery_state(directory: str | Path) -> RecoveryState:
    """Read durable inputs without applying them or producing new writes."""

    root = Path(directory)
    checkpoint = read_checkpoint(root / "checkpoint.bin") or {
        "sequence": 0,
        "collections": {},
    }
    return RecoveryState(
        checkpoint_sequence=checkpoint["sequence"],
        collections=checkpoint["collections"],
        journal_entries=Journal(root / "journal.bin").read_entries(repair=True),
    )
