"""Labs must stay executable scripts built only on the public package API."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize(
    ("script", "markers"),
    [
        (
            "lab_array_matching.py",
            ["scalar array match", "literal nested document", "dotted path match"],
        ),
        (
            "lab_oplog_idempotent.py",
            ["requested $inc", "stored oplog payload", "same after replay twice: True"],
        ),
        (
            "lab_crash_recovery.py",
            ["before injected crash", "truncated journal tail", "recovered documents"],
        ),
        (
            "lab_multikey_index.py",
            ["one document", "index keys", "matched document ids"],
        ),
        (
            "lab_explain.py",
            ["before index: COLLSCAN", "after index: IXSCAN", "docs examined"],
        ),
    ],
)
def test_lab_runs_as_a_script(script: str, markers: list[str]) -> None:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")
    completed = subprocess.run(
        [sys.executable, str(ROOT / "labs" / script)],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    assert all(marker in completed.stdout for marker in markers)
