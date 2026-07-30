"""Index boundaries; M1 implements only the mandatory unique ``_id`` index."""

from minimongodb.index.id_index import IdIndex

__all__ = ["IdIndex"]
