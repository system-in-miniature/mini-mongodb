"""Atomic whole-database snapshots for the single-writer teaching engine."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from minimongodb.storage.codec import decode_value, encode_value


def write_checkpoint(path: str | Path, state: dict[str, Any]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    payload = encode_value(state)
    with temporary.open("wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, destination)


def read_checkpoint(path: str | Path) -> dict[str, Any] | None:
    source = Path(path)
    if not source.exists():
        return None
    value = decode_value(source.read_bytes())
    if not isinstance(value, dict):
        raise ValueError("checkpoint root must be a document")
    return value
