from __future__ import annotations

from pathlib import Path

import pytest
from conftest import git

from autobuild.gitops import (
    CandidateArtifactError,
    GitError,
    cleanup_succeeded_worktree,
    commit_candidate,
    create_worktree,
    current_commit,
    measure_change_surface,
    promote_fast_forward,
)


def test_candidate_promotes_by_fast_forward(git_repository: Path) -> None:
    base = current_commit(git_repository)
    worktree = create_worktree(
        git_repository,
        git_repository / ".autobuild" / "worktrees",
        "run-one",
        "task",
        base,
    )
    (worktree.path / "candidate.txt").write_text("verified\n", encoding="utf-8")
    candidate = commit_candidate(worktree, "candidate")

    promoted = promote_fast_forward(git_repository, worktree, base)

    assert promoted == candidate
    assert (git_repository / "candidate.txt").read_text(encoding="utf-8") == "verified\n"

    cleanup_succeeded_worktree(
        git_repository,
        git_repository / ".autobuild" / "worktrees",
        worktree,
        promoted,
    )

    assert not worktree.path.exists()
    assert worktree.branch not in git(git_repository, "branch", "--list")


def test_base_change_prevents_promotion(git_repository: Path) -> None:
    base = current_commit(git_repository)
    worktree = create_worktree(
        git_repository,
        git_repository / ".autobuild" / "worktrees",
        "run-two",
        "task",
        base,
    )
    (worktree.path / "candidate.txt").write_text("candidate\n", encoding="utf-8")
    commit_candidate(worktree, "candidate")
    (git_repository / "base.txt").write_text("changed\n", encoding="utf-8")
    git(git_repository, "add", "base.txt")
    git(git_repository, "commit", "-m", "advance base")

    with pytest.raises(GitError, match="base commit changed"):
        promote_fast_forward(git_repository, worktree, base)


def test_committed_change_surface_counts_files_and_lines(git_repository: Path) -> None:
    base = current_commit(git_repository)
    worktree = create_worktree(
        git_repository,
        git_repository / ".autobuild" / "worktrees",
        "run-quality",
        "task",
        base,
    )
    (worktree.path / "README.md").write_text("# revised\n", encoding="utf-8")
    (worktree.path / "candidate.txt").write_text("one\ntwo\n", encoding="utf-8")
    candidate = commit_candidate(worktree, "candidate quality")

    quality = measure_change_surface(worktree.path, base, candidate)

    assert quality.changed_files == 2
    assert quality.insertions == 3
    assert quality.deletions == 1
    assert quality.changed_lines == 4


def test_candidate_commit_rejects_nested_git_repository(
    git_repository: Path,
) -> None:
    base = current_commit(git_repository)
    worktree = create_worktree(
        git_repository,
        git_repository / ".autobuild" / "worktrees",
        "run-nested",
        "task",
        base,
    )
    nested_paths = [
        worktree.path / "generated-repository",
        worktree.path / "second-generated-repository",
    ]
    for nested in nested_paths:
        nested.mkdir()
        git(nested, "init")
        git(nested, "config", "user.name", "Autobuild Test")
        git(nested, "config", "user.email", "autobuild@example.invalid")
        (nested / "generated.txt").write_text("generated\n", encoding="utf-8")
        git(nested, "add", "generated.txt")
        git(nested, "commit", "-m", "generated repository")

    with pytest.raises(
        CandidateArtifactError,
        match=(
            "candidate adds nested Git repositories: "
            "generated-repository, second-generated-repository"
        ),
    ):
        commit_candidate(worktree, "candidate")

    assert current_commit(worktree.path) == base
    assert all(nested.exists() for nested in nested_paths)


def test_cleanup_preserves_dirty_successful_worktree(git_repository: Path) -> None:
    base = current_commit(git_repository)
    worktree = create_worktree(
        git_repository,
        git_repository / ".autobuild" / "worktrees",
        "run-dirty",
        "task",
        base,
    )
    (worktree.path / "candidate.txt").write_text("candidate\n", encoding="utf-8")
    candidate = commit_candidate(worktree, "candidate")
    promote_fast_forward(git_repository, worktree, base)
    (worktree.path / "uncommitted.txt").write_text("preserve\n", encoding="utf-8")

    with pytest.raises(GitError, match="uncommitted changes"):
        cleanup_succeeded_worktree(
            git_repository,
            git_repository / ".autobuild" / "worktrees",
            worktree,
            candidate,
        )

    assert worktree.path.exists()
