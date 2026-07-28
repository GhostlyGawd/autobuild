from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


def git(root: Path, *arguments: str) -> str:
    process = subprocess.run(
        ("git", *arguments),
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        shell=False,
    )
    if process.returncode != 0:
        raise AssertionError(process.stderr or process.stdout)
    return process.stdout.strip()


def write_spec(root: Path, *, item_id: str = "task", kind: str = "product") -> None:
    data = {
        "schema_version": 1,
        "objective": "Prove the controller lifecycle.",
        "writing_policy": {
            "mode": "controlled-technical-english",
            "asd_ste100_release_claim": "human-review-required",
        },
        "work_items": [
            {
                "id": item_id,
                "kind": kind,
                "priority": 10,
                "objective": "Create a verified candidate.",
                "acceptance": ["The candidate passes the configured gate."],
            }
        ],
    }
    (root / "SPEC.json").write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def git_repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    root.mkdir()
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "Autobuild Test")
    git(root, "config", "user.email", "autobuild@example.invalid")
    (root / ".gitignore").write_text(
        ".autobuild/state.db*\n.autobuild/worktrees/\n.autobuild/results/\n",
        encoding="utf-8",
    )
    (root / "README.md").write_text("# test\n", encoding="utf-8")
    write_spec(root)
    git(root, "add", "--all")
    git(root, "commit", "-m", "initial")
    return root

