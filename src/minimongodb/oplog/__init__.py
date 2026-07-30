"""Logical write log whose entries can safely be replayed more than once."""

from minimongodb.oplog.entry import Oplog, OplogEntry


def replay(*args, **kwargs):
    """Import the collection-aware replayer lazily to avoid an API cycle."""

    from minimongodb.oplog.replay import replay as replay_entries

    return replay_entries(*args, **kwargs)

__all__ = ["Oplog", "OplogEntry", "replay"]
