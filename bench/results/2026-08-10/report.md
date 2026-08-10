# MiniMongoDB planner-work report

Across 100, 1,000, and 10,000 documents with 1% selectivity, COLLSCAN examined
every document while `kind_1` IXSCAN examined only the matching 1%. At 10,000
documents this changed 10,000 documents examined to 100: a deterministic 100x
work reduction. All result lists remained equal before and after indexing.

This is an explain-counter comparison inside a Python teaching kernel. It is
not an elapsed-time speedup or a production MongoDB capacity claim.
