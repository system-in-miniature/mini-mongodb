"""Contracts for content-driven MiniMongoDB Stage reconstruction."""

import subprocess
from pathlib import Path

from journey.tools import extract_history

ROOT = Path(__file__).resolve().parents[3]


def test_manifest_is_eight_contiguous_content_driven_stages() -> None:
    manifest = extract_history.load_manifest(ROOT / "journey" / "manifest.toml")

    assert [stage.number for stage in manifest.stages] == list(range(1, 9))
    assert manifest.stages[4].source == "4365a53"
    assert manifest.stages[-1].slug == "executable-domain-labs"


def test_regression_stages_replace_their_earlier_owned_files() -> None:
    manifest = extract_history.load_manifest(ROOT / "journey" / "manifest.toml")
    before_ordering = extract_history.snapshot_for_stage(manifest, 4, root=ROOT)
    after_ordering = extract_history.snapshot_for_stage(manifest, 5, root=ROOT)
    assert before_ordering["src/minimongodb/collection.py"] != after_ordering[
        "src/minimongodb/collection.py"
    ]

    before_validation = extract_history.snapshot_for_stage(manifest, 6, root=ROOT)
    after_validation = extract_history.snapshot_for_stage(manifest, 7, root=ROOT)
    assert before_validation["src/minimongodb/query/matcher.py"] != after_validation[
        "src/minimongodb/query/matcher.py"
    ]


def test_final_snapshot_matches_every_owned_reference_byte() -> None:
    manifest = extract_history.load_manifest(ROOT / "journey" / "manifest.toml")
    final = extract_history.snapshot_for_stage(manifest, 8, root=ROOT)
    assert final == extract_history.owned_tree(ROOT, manifest)


def test_generated_patches_apply_cleanly_and_reach_each_snapshot(
    tmp_path: Path,
) -> None:
    manifest = extract_history.load_manifest(ROOT / "journey" / "manifest.toml")
    workspace = tmp_path / "rebuilt"
    workspace.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)

    for stage in manifest.stages:
        patch = extract_history.patch_for_stage(manifest, stage.number, root=ROOT)
        patch_path = tmp_path / f"stage-{stage.number:02d}.patch"
        patch_path.write_bytes(patch)
        subprocess.run(
            ["git", "apply", "--check", str(patch_path)], cwd=workspace, check=True
        )
        subprocess.run(["git", "apply", str(patch_path)], cwd=workspace, check=True)
        expected = extract_history.snapshot_for_stage(manifest, stage.number, root=ROOT)
        actual = {
            path.relative_to(workspace).as_posix(): path.read_bytes()
            for path in workspace.rglob("*")
            if path.is_file() and ".git" not in path.parts
        }
        assert actual == expected
