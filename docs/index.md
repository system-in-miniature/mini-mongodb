# MiniMongoDB Tutorial

[中文版](zh/index.md)

MiniMongoDB is a deterministic, single-process Python document-database kernel
for learning dotted paths, array-aware matching, canonical multikey indexes,
COLLSCAN/IXSCAN planning, aggregation pipelines, idempotent post-image oplogs,
CRC-framed journals, checkpoints, and startup recovery. It is not a
MongoDB-compatible server.

## Install

You need Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/system-in-miniature/MiniMongoDB.git
cd MiniMongoDB
uv sync
```

## First experiment

```bash
uv run python labs/lab_array_matching.py
```

The output shows that a scalar predicate matches an element of a stored array,
an incomplete embedded-document literal does not equal the whole document, and
a dotted path selects the nested field directly.

## Reading path

Start with the repository's end-to-end data path and directory guide. Read the
mapping next, run all five labs, and finish with the differences chapter to
keep this M2 teaching model separate from production MongoDB semantics.

The [English README](https://github.com/system-in-miniature/MiniMongoDB#readme)
contains the complete implemented scope and persistent API example. The
[design history archive](superpowers/README.md) records construction-time
plans; canonical docs and tests define current behavior.
