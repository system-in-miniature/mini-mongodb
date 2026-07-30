"""M2 placeholder for ``$match/$project/$group/$sort/$limit`` pipelines.

The future package will model aggregation stages as a pull-based operator
stream so it can be compared directly with MiniPostgres' relational execution
operators.  M1 does not accept aggregation syntax or pretend a list
comprehension is a complete pipeline.
"""
