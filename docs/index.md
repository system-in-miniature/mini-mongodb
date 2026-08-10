# MiniMongoDB: A Document Database in Miniature

> English · [Chinese](zh/index.md)

MiniMongoDB is a deterministic, single-process Python kernel for learning how
a document database owns values, matches arrays, applies atomic updates, makes
writes durable, replays an oplog, maintains multikey indexes, chooses query
plans, and executes aggregation pipelines.

## Learning modes

- **[Mechanism Tutorial](tutorial/01-getting-started.md)** — study document
  values, queries, updates, durability, oplogs, indexes, planning, and
  aggregation in dependency order.
- **[Self-Guided Rebuild](journey/index.md)** — rebuild the kernel through eight
  browser-native Stages with test contracts and grouped code differences.
- **[Agent-Guided Rebuild](agent-guide.md)** — ask Codex to teach, implement,
  explain, and verify one Stage interactively.

## Before you begin

```bash
git clone https://github.com/system-in-miniature/mini-mongodb.git
cd mini-mongodb
uv sync
uv run pytest -q
```

MiniMongoDB is an in-process teaching kernel, not a MongoDB-compatible server.
Keep the [mechanism mapping](mapping.md), [declared differences](DIFFERENCES.md),
and [lab guide](labs-guide.md) beside the tutorial.
