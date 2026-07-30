"""M3 placeholder for capped oplog retention.

M1 intentionally keeps an unbounded in-memory sequence plus durable journal.
M3 will replace the backing list with a bounded ring while preserving the
``OplogEntry`` and replay contracts.  No fake capped behavior is exposed here.
"""
