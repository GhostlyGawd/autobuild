from __future__ import annotations

import sys
from pathlib import Path

import pytest

import autobuild.orchestrator as orchestrator_module
from autobuild.config import AgentConfig, Config, PolicyConfig
from autobuild.gitops import GitError, current_commit
from autobuild.models import Gate
from autobuild.orchestrator import Orchestrator


def config_for(
    root: Path,
    *,
    gate_exit: int,
    gate_code: str | None = None,
    auto_promote: bool = True,
) -> Config:
    return Config(
        root=root,
        state_path=root / ".autobuild" / "state.db",
        worktree_root=root / ".autobuild" / "worktrees",
        result_root=root / ".autobuild" / "results",
        lease_seconds=60,
        max_attempts=3,
        auto_promote=auto_promote,
        agent=AgentConfig(
            kind="fake",
            command=(
                sys.executable,
                "-c",
                "from pathlib import Path; Path('candidate.txt').write_text('candidate\\n')",
            ),
            timeout_seconds=10,
        ),
        policy=PolicyConfig(
            allowed_environment=frozenset({"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR"}),
            redacted_name_fragments=("TOKEN", "SECRET"),
        ),
        gates=(
            Gate(
                name="result",
                command=(
                    sys.executable,
                    "-c",
                    gate_code or f"raise SystemExit({gate_exit})",
                ),
                timeout_seconds=10,
            ),
        ),
    )


def test_gate_failure_prevents_promotion_and_preserves_worktree(
    git_repository: Path,
) -> None:
    base = current_commit(git_repository)

    outcome = Orchestrator(
        git_repository, config_for(git_repository, gate_exit=1)
    ).reconcile_once()

    assert outcome.status == "failed"
    assert outcome.detail == "gate failed: result"
    assert current_commit(git_repository) == base
    assert outcome.worktree is not None
    assert (outcome.worktree / "candidate.txt").exists()


def test_success_promotes_candidate_and_marks_item_achieved(
    git_repository: Path,
) -> None:
    base = current_commit(git_repository)
    orchestrator = Orchestrator(
        git_repository, config_for(git_repository, gate_exit=0)
    )

    outcome = orchestrator.reconcile_once()

    assert outcome.status == "succeeded"
    assert current_commit(git_repository) != base
    assert (git_repository / "candidate.txt").read_text(encoding="utf-8") == "candidate\n"
    assert orchestrator.store.status()["work_items"][0]["status"] == "achieved"


def test_gate_mutation_prevents_promotion(git_repository: Path) -> None:
    base = current_commit(git_repository)
    gate_code = (
        "from pathlib import Path; "
        "Path('post-gate.txt').write_text('unverified\\n'); "
        "raise SystemExit(0)"
    )

    outcome = Orchestrator(
        git_repository,
        config_for(git_repository, gate_exit=0, gate_code=gate_code),
    ).reconcile_once()

    assert outcome.status == "failed"
    assert outcome.detail == "verification gates changed the candidate"
    assert current_commit(git_repository) == base
    assert outcome.worktree is not None
    assert (outcome.worktree / "post-gate.txt").exists()


def test_git_error_in_promotion_records_terminal_failure(
    git_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_promotion(*_args, **_kwargs):
        raise GitError("injected promotion failure")

    monkeypatch.setattr(
        orchestrator_module,
        "promote_fast_forward",
        fail_promotion,
    )
    orchestrator = Orchestrator(
        git_repository,
        config_for(git_repository, gate_exit=0),
    )

    outcome = orchestrator.reconcile_once()

    assert outcome.status == "failed"
    assert orchestrator.store.status()["recent_runs"][0]["status"] == "failed"


def test_manual_promotion_policy_enters_stable_handoff(
    git_repository: Path,
) -> None:
    orchestrator = Orchestrator(
        git_repository,
        config_for(git_repository, gate_exit=0, auto_promote=False),
    )

    outcome = orchestrator.reconcile_once()

    assert outcome.status == "awaiting-promotion"
    assert orchestrator.store.status()["recent_runs"][0]["status"] == "awaiting-promotion"
    assert orchestrator.store.status()["work_items"][0]["status"] == "blocked"
