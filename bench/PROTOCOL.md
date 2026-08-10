# MiniMongoDB evidence protocol

> English · [Chinese](PROTOCOL.zh-CN.md)

This is a deterministic mechanism benchmark for a teaching kernel, not a
production MongoDB latency or capacity comparison. It measures planner work,
using public `Collection.explain()` counters rather than unstable wall time.

The fixed fixture has 100, 1,000, and 10,000 documents. Exactly one document in
every 100 has `kind="rare"`. For each scale, the harness runs the same query
before and after building `kind_1`, records the winning stage, documents and
keys examined, and verifies byte-for-byte-equivalent returned Python values.

Run from the repository root:

```bash
uv run python -m bench.run --output bench/results/2026-08-10/results.json
uv run python -m pytest -q bench/tests
```

Document counts and the query are fixed; there is no random seed. Environment
metadata is retained for provenance, but the primary metric is a deterministic
operation count. Do not interpret it as elapsed-time speedup.
