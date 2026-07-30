"""M2 placeholder for COLLSCAN/IXSCAN planning and ``explain``.

M1 always scans the deterministic in-memory document list, except that the
private ``_id`` map enforces uniqueness and supports recovery identity lookup.
M2 will add plan nodes, selection estimates, secondary-index scans, and public
explain statistics.  No callable planner is exposed early.
"""
