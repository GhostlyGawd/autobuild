"""Git isolation, observation, and fast-forward promotion."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitError(RuntimeError):
    """A Git invariant or command failed."""


def _git(root: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(
        ("git", *arguments),
        cwd=root,
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )
    if check and process.returncode != 0:
        raise GitError(process.stderr.strip() or process.stdout.strip())
    return process


def current_commit(root: Path) -> str:
    return _git(root, "rev-parse", "HEAD").stdout.strip()


def is_clean(root: Path) -> bool:
    return not _git(root, "status", "--porcelain").stdout.strip()


def _safe_fragment(value: str) -> str:
    fragment = re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-._")
    if not fragment:
        raise GitError("work item id does not contain a safe branch fragment")
    return fragment[:60]


@dataclass(frozen=True)
class Worktree:
    path: Path
    branch: str
    base_commit: str


def create_worktree(
    root: Path,
    worktree_root: Path,
    run_id: str,
    item_id: str,
    expected_base: str,
) -> Worktree:
    if current_commit(root) != expected_base:
        raise GitError("base commit changed before worktree creation")
    branch = f"autobuild/{_safe_fragment(item_id)}/{run_id[:8]}"
    path = (worktree_root / run_id).resolve()
    try:
        path.relative_to(worktree_root.resolve())
    except ValueError as error:
        raise GitError("worktree path escaped the configured root") from error
    if path.exists():
        raise GitError(f"worktree path already exists: {path}")
    worktree_root.mkdir(parents=True, exist_ok=True)
    _git(root, "worktree", "add", "-b", branch, str(path), expected_base)
    return Worktree(path=path, branch=branch, base_commit=expected_base)


def has_changes(worktree: Worktree) -> bool:
    return bool(_git(worktree.path, "status", "--porcelain").stdout.strip())


def commit_candidate(worktree: Worktree, message: str) -> str:
    if has_changes(worktree):
        _git(worktree.path, "add", "--all")
        _git(worktree.path, "commit", "-m", message)
    return current_commit(worktree.path)


def promote_fast_forward(root: Path, worktree: Worktree, expected_base: str) -> str:
    if not is_clean(root):
        raise GitError("base repository changed before promotion")
    if current_commit(root) != expected_base:
        raise GitError("base commit changed before promotion")
    candidate = current_commit(worktree.path)
    merge_base = _git(root, "merge-base", expected_base, candidate).stdout.strip()
    if merge_base != expected_base:
        raise GitError("candidate is not a descendant of the expected base")
    _git(root, "merge", "--ff-only", candidate)
    return current_commit(root)
