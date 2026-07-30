"""Domain errors keep expected database failures separate from Python bugs."""


class MiniMongoError(Exception):
    """Base class for errors intentionally exposed by MiniMongoDB."""


class DuplicateKeyError(MiniMongoError):
    """Raised when the unique ``_id`` index already contains a key."""


class ImmutableIdError(MiniMongoError):
    """Raised when an update attempts to change or remove ``_id``."""


class InvalidQueryError(MiniMongoError):
    """Raised for unsupported or malformed query expressions."""


class InvalidUpdateError(MiniMongoError):
    """Raised for malformed updates or incompatible operand types."""


class PathError(MiniMongoError):
    """Raised when a dotted path cannot traverse the current container."""


class JournalCorruptionError(MiniMongoError):
    """Raised when corruption occurs before the repairable journal tail."""
