"""Canonical identity and secondary index structures."""

from minimongodb.index.id_index import IdIndex
from minimongodb.index.secondary import (
    SecondaryIndex,
    default_index_name,
    normalize_index_spec,
)

__all__ = [
    "IdIndex",
    "SecondaryIndex",
    "default_index_name",
    "normalize_index_spec",
]
