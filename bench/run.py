"""Measure deterministic planner work reduction at fixed collection scales."""

from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path

from minimongodb import Collection


def measure(size: int) -> dict[str, object]:
    collection = Collection("events")
    collection.insert_many(
        {"_id": index, "kind": "rare" if index % 100 == 0 else "common"}
        for index in range(size)
    )
    query = {"kind": "rare"}
    before = collection.explain(query)
    expected = collection.find(query)
    collection.create_index("kind")
    after = collection.explain(query)
    actual = collection.find(query)
    before_stats = before["executionStats"]
    after_stats = after["executionStats"]
    return {
        "documents": size,
        "matches": len(actual),
        "before_stage": before["queryPlanner"]["winningPlan"]["stage"],
        "after_stage": after["queryPlanner"]["winningPlan"]["stage"],
        "before_docs_examined": before_stats["docsExamined"],
        "after_docs_examined": after_stats["docsExamined"],
        "after_keys_examined": after_stats["keysExamined"],
        "work_reduction": before_stats["docsExamined"] / after_stats["docsExamined"],
        "results_equal": expected == actual,
    }


def build_results() -> dict[str, object]:
    return {
        "protocol_version": 1,
        "fixture": {"rare_every": 100, "query": {"kind": "rare"}},
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "measurements": [measure(size) for size in (100, 1_000, 10_000)],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results = build_results()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
