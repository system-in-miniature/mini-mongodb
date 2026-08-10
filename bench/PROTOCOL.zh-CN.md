# MiniMongoDB 证据实验协议

> [English](PROTOCOL.md) · 简体中文

这是教学内核的确定性机制基准，不是生产 MongoDB 延迟或容量对比。它使用公共
`Collection.explain()` 计数测量 Planner 工作量，不使用不稳定的墙钟时间。

固定夹具包含 100、1,000、10,000 个文档，每 100 个文档恰有一个
`kind="rare"`。每个规模都在创建 `kind_1` 前后运行相同查询，记录 Winning
Stage、Docs/Keys Examined，并验证返回的 Python 值完全一致。

```bash
uv run python -m bench.run --output bench/results/2026-08-10/results.json
uv run python -m pytest -q bench/tests
```

文档数和 Query 固定，因此无需随机种子。主要指标是确定性操作计数，不能解释为
耗时加速比。
