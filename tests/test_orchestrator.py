from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest
from conftest import git, write_spec

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
    lease_seconds: int = 60,
    agent_code: str | None = None,
) -> Config:
    return Config(
        root=root,
        state_path=root / ".autobuild" / "state.db",
        worktree_root=root / ".autobuild" / "worktrees",
        result_root=root / ".autobuild" / "results",
        lease_seconds=lease_seconds,
        max_attempts=3,
        auto_promote=auto_promote,
        agent=AgentConfig(
            kind="fake",
            command=(
                sys.executable,
                "-c",
                agent_code
                or "from pathlib import Path; Path('candidate.txt').write_text('candidate\\n')",
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

    assert outcome.status == "succeeded", outcome.detail
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


def test_long_agent_renews_short_lease(git_repository: Path) -> None:
    agent_code = (
        "import time; "
        "from pathlib import Path; "
        "time.sleep(2.4); "
        "Path('candidate.txt').write_text('candidate\\n')"
    )
    orchestrator = Orchestrator(
        git_repository,
        config_for(
            git_repository,
            gate_exit=0,
            lease_seconds=2,
            agent_code=agent_code,
        ),
    )

    outcome = orchestrator.reconcile_once()

    assert outcome.status == "succeeded", outcome.detail
    assert orchestrator.store.status()["recent_runs"][0]["status"] == "succeeded"


def test_dispatch_stops_after_spec_change(
    git_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orchestrator = Orchestrator(
        git_repository,
        config_for(git_repository, gate_exit=0),
    )
    original_claim = orchestrator.store.claim_next

    def claim_then_change_spec(*args, **kwargs):
        claim = original_claim(*args, **kwargs)
        write_spec(git_repository, item_id="changed-task")
        return claim

    monkeypatch.setattr(orchestrator.store, "claim_next", claim_then_change_spec)

    outcome = orchestrator.reconcile_once()

    assert outcome.status == "stale"
    assert outcome.detail == "desired state changed before dispatch"
    assert outcome.worktree is None


def test_dispatch_stops_after_base_change(
    git_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orchestrator = Orchestrator(
        git_repository,
        config_for(git_repository, gate_exit=0),
    )
    original_claim = orchestrator.store.claim_next

    def claim_then_change_base(*args, **kwargs):
        claim = original_claim(*args, **kwargs)
        (git_repository / "concurrent.txt").write_text("changed\n", encoding="utf-8")
        git(git_repository, "add", "concurrent.txt")
        git(git_repository, "commit", "-m", "concurrent base change")
        return claim

    monkeypatch.setattr(orchestrator.store, "claim_next", claim_then_change_base)

    outcome = orchestrator.reconcile_once()

    assert outcome.status == "stale"
    assert outcome.detail == "desired state changed before dispatch"
    assert outcome.worktree is None


def test_agent_startup_error_records_terminal_failure(git_repository: Path) -> None:
    config = config_for(git_repository, gate_exit=0)
    config = replace(
        config,
        agent=AgentConfig(
            kind="missing",
            command=("autobuild-executable-that-does-not-exist",),
            timeout_seconds=10,
        ),
    )
    orchestrator = Orchestrator(git_repository, config)

    outcome = orchestrator.reconcile_once()

    assert outcome.status == "failed"
    assert "executable not found" in outcome.detail
    assert orchestrator.store.status()["recent_runs"][0]["status"] == "failed"
