"""Git isolation, observation, and fast-forward promotion."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .models import ChangeSurface


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


def measure_change_surface(
    root: Path,
    base_commit: str,
    candidate_commit: str,
) -> ChangeSurface:
    ancestor = _git(
        root,
        "merge-base",
        "--is-ancestor",
        base_commit,
        candidate_commit,
        check=False,
    )
    if ancestor.returncode != 0:
        raise GitError("candidate is not a descendant of the claimed base")
    result = _git(
        root,
        "diff",
        "--numstat",
        "-z",
        "--no-renames",
        "--no-ext-diff",
        "--no-textconv",
        base_commit,
        candidate_commit,
        "--",
    )
    changed_files = 0
    insertions = 0
    deletions = 0
    for record in result.stdout.split("\0"):
        if not record:
            continue
        fields = record.split("\t", 2)
        if len(fields) != 3:
            raise GitError("Git returned an invalid change-surface record")
        added, deleted, _path = fields
        try:
            insertions += 0 if added == "-" else int(added)
            deletions += 0 if deleted == "-" else int(deleted)
        except ValueError as error:
            raise GitError("Git returned an invalid change-surface count") from error
        changed_files += 1
    return ChangeSurface(
        changed_files=changed_files,
        insertions=insertions,
        deletions=deletions,
        changed_lines=insertions + deletions,
    )


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


def cleanup_succeeded_worktree(
    root: Path,
    worktree_root: Path,
    worktree: Worktree,
    promoted_commit: str,
) -> None:
    path = worktree.path.resolve()
    try:
        path.relative_to(worktree_root.resolve())
    except ValueError as error:
        raise GitError("cleanup path escaped the configured worktree root") from error
    if not path.is_dir():
        raise GitError("successful worktree is not present")
    if not is_clean(path):
        raise GitError("successful worktree has uncommitted changes")
    if current_commit(path) != promoted_commit:
        raise GitError("successful worktree does not match the promoted commit")
    ancestor = _git(
        root,
        "merge-base",
        "--is-ancestor",
        promoted_commit,
        current_commit(root),
        check=False,
    )
    if ancestor.returncode != 0:
        raise GitError("promoted commit is not reachable from the base repository")
    registered = {
        Path(line.removeprefix("worktree ")).resolve()
        for line in _git(root, "worktree", "list", "--porcelain").stdout.splitlines()
        if line.startswith("worktree ")
    }
    if path not in registered:
        raise GitError("cleanup target is not a registered Git worktree")
    _git(root, "worktree", "remove", str(path))
    _git(root, "branch", "--delete", worktree.branch)
