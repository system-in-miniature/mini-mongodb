"""Mongo-shaped query matching over in-memory teaching documents."""

from minimongodb.query.matcher import matches, resolve_path

__all__ = ["matches", "resolve_path"]
