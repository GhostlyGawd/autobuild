from __future__ import annotations

from pathlib import Path

import pytest
from conftest import git

from autobuild.gitops import (
    GitError,
    commit_candidate,
    create_worktree,
    current_commit,
    promote_fast_forward,
)


def test_candidate_promotes_by_fast_forward(git_repository: Path) -> None:
    base = current_commit(git_repository)
    worktree = create_worktree(
        git_repository,
        git_repository / ".autobuild" / "worktrees",
        "run-one",
        "task",
    )
    (worktree.path / "candidate.txt").write_text("verified\n", encoding="utf-8")
    candidate = commit_candidate(worktree, "candidate")

    promoted = promote_fast_forward(git_repository, worktree, base)

    assert promoted == candidate
    assert (git_repository / "candidate.txt").read_text(encoding="utf-8") == "verified\n"


def test_base_change_prevents_promotion(git_repository: Path) -> None:
    base = current_commit(git_repository)
    worktree = create_worktree(
        git_repository,
        git_repository / ".autobuild" / "worktrees",
        "run-two",
        "task",
    )
    (worktree.path / "candidate.txt").write_text("candidate\n", encoding="utf-8")
    commit_candidate(worktree, "candidate")
    (git_repository / "base.txt").write_text("changed\n", encoding="utf-8")
    git(git_repository, "add", "base.txt")
    git(git_repository, "commit", "-m", "advance base")

    with pytest.raises(GitError, match="base commit changed"):
        promote_fast_forward(git_repository, worktree, base)
