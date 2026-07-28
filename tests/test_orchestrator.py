from __future__ import annotations

import json
import sqlite3
import sys
import threading
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest
from conftest import git, write_spec

import autobuild.orchestrator as orchestrator_module
import autobuild.state as state_module
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
        cleanup_succeeded_worktrees=True,
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
    assert outcome.worktree is not None
    assert not outcome.worktree.exists()
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


def test_concurrent_controller_cannot_dispatch_while_owner_is_current(
    git_repository: Path,
) -> None:
    started_marker = git_repository.parent / "controller-agent-started"
    agent_code = (
        "import time; "
        "from pathlib import Path; "
        f"Path({str(started_marker)!r}).write_text('started'); "
        "time.sleep(1.5); "
        "Path('candidate.txt').write_text('candidate\\n')"
    )
    config = config_for(
        git_repository,
        gate_exit=0,
        lease_seconds=5,
        agent_code=agent_code,
    )
    first = Orchestrator(git_repository, config)
    second = Orchestrator(git_repository, config)
    first_outcomes = []

    thread = threading.Thread(
        target=lambda: first_outcomes.append(first.reconcile_once()),
        daemon=True,
    )
    thread.start()
    for _ in range(500):
        if started_marker.exists():
            break
        time.sleep(0.01)
    else:
        raise AssertionError("first controller did not dispatch its agent")

    second_outcome = second.reconcile_once()
    thread.join(timeout=10)

    assert second_outcome.status == "deferred"
    assert second_outcome.run_id is None
    assert "another current owner" in second_outcome.detail
    assert len(first_outcomes) == 1
    assert first_outcomes[0].status == "succeeded"
    with sqlite3.connect(config.state_path) as connection:
        run_count = connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    assert run_count == 1


def test_controller_restart_recovers_after_ownership_expiry(
    git_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = datetime(2026, 7, 28, tzinfo=UTC)
    monkeypatch.setattr(state_module, "_now", lambda: clock)
    config = config_for(git_repository, gate_exit=0, lease_seconds=1)
    crashed = Orchestrator(git_repository, config)
    crashed.store.initialize()
    crashed.store.acquire_controller_lease(
        git_repository,
        1,
        owner_id="crashed-controller",
    )

    blocked = Orchestrator(git_repository, config).reconcile_once()
    clock += timedelta(seconds=2)
    recovered = Orchestrator(git_repository, config).reconcile_once()

    assert blocked.status == "deferred"
    assert recovered.status == "succeeded", recovered.detail
    status = crashed.store.status()
    assert status["controller_lease"]["active"] is False
    with sqlite3.connect(config.state_path) as connection:
        generations = [
            json.loads(row[0])["generation"]
            for row in connection.execute(
                """
                SELECT payload_json FROM events
                WHERE kind = 'controller_acquired'
                ORDER BY sequence
                """
            )
        ]
    assert generations == [1, 2]


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
    assert outcome.detail == "authority lost: spec-digest-changed"
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
    assert outcome.detail == "authority lost: base-commit-changed"
    assert outcome.worktree is None


def test_active_agent_stops_after_spec_authority_loss(
    git_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started_marker = git_repository.parent / "agent-started"
    evaluated_marker = git_repository.parent / "candidate-evaluated"
    agent_code = (
        "import time; "
        "from pathlib import Path; "
        f"Path({str(started_marker)!r}).write_text('started'); "
        "time.sleep(5); "
        "Path('candidate.txt').write_text('candidate\\n')"
    )
    gate_code = (
        "from pathlib import Path; "
        f"Path({str(evaluated_marker)!r}).write_text('evaluated')"
    )
    orchestrator = Orchestrator(
        git_repository,
        config_for(
            git_repository,
            gate_exit=0,
            lease_seconds=2,
            agent_code=agent_code,
            gate_code=gate_code,
        ),
    )
    renew_lease = Mock(wraps=orchestrator.store.renew_lease)
    monkeypatch.setattr(orchestrator.store, "renew_lease", renew_lease)
    base = current_commit(git_repository)
    thread_errors: list[BaseException] = []

    def change_spec_when_agent_starts() -> None:
        try:
            for _ in range(500):
                if started_marker.exists():
                    write_spec(git_repository, item_id="changed-task")
                    return
                time.sleep(0.01)
            raise AssertionError("agent did not start")
        except BaseException as error:
            thread_errors.append(error)

    changer = threading.Thread(target=change_spec_when_agent_starts, daemon=True)
    changer.start()
    started = time.monotonic()

    outcome = orchestrator.reconcile_once()

    changer.join(timeout=2)
    assert not thread_errors
    assert outcome.status == "stale"
    assert outcome.detail == "authority lost: spec-digest-changed"
    assert time.monotonic() - started < 4
    assert current_commit(git_repository) == base
    assert outcome.worktree is not None
    assert not (outcome.worktree / "candidate.txt").exists()
    assert not evaluated_marker.exists()
    assert renew_lease.call_count == 0
    with sqlite3.connect(orchestrator.config.state_path) as connection:
        event = connection.execute(
            """
            SELECT payload_json FROM events
            WHERE run_id = ? AND kind = 'authority_lost'
            """,
            (outcome.run_id,),
        ).fetchone()
    assert event is not None
    assert json.loads(event[0]) == {"cause": "spec-digest-changed"}


def test_active_agent_stops_after_base_commit_authority_loss(
    git_repository: Path,
) -> None:
    started_marker = git_repository.parent / "agent-started"
    evaluated_marker = git_repository.parent / "candidate-evaluated"
    agent_code = (
        "import time; "
        "from pathlib import Path; "
        f"Path({str(started_marker)!r}).write_text('started'); "
        "time.sleep(5); "
        "Path('candidate.txt').write_text('candidate\\n')"
    )
    gate_code = (
        "from pathlib import Path; "
        f"Path({str(evaluated_marker)!r}).write_text('evaluated')"
    )
    orchestrator = Orchestrator(
        git_repository,
        config_for(
            git_repository,
            gate_exit=0,
            lease_seconds=2,
            agent_code=agent_code,
            gate_code=gate_code,
        ),
    )
    base = current_commit(git_repository)
    thread_errors: list[BaseException] = []

    def change_base_when_agent_starts() -> None:
        try:
            for _ in range(500):
                if started_marker.exists():
                    (git_repository / "concurrent.txt").write_text(
                        "changed\n",
                        encoding="utf-8",
                    )
                    git(git_repository, "add", "concurrent.txt")
                    git(git_repository, "commit", "-m", "concurrent base change")
                    return
                time.sleep(0.01)
            raise AssertionError("agent did not start")
        except BaseException as error:
            thread_errors.append(error)

    changer = threading.Thread(target=change_base_when_agent_starts, daemon=True)
    changer.start()
    started = time.monotonic()

    outcome = orchestrator.reconcile_once()

    changer.join(timeout=2)
    assert not thread_errors
    assert outcome.status == "stale"
    assert outcome.detail == "authority lost: base-commit-changed"
    assert time.monotonic() - started < 4
    assert current_commit(git_repository) != base
    assert not (git_repository / "candidate.txt").exists()
    assert outcome.worktree is not None
    assert not (outcome.worktree / "candidate.txt").exists()
    assert not evaluated_marker.exists()
    with sqlite3.connect(orchestrator.config.state_path) as connection:
        event = connection.execute(
            """
            SELECT payload_json FROM events
            WHERE run_id = ? AND kind = 'authority_lost'
            """,
            (outcome.run_id,),
        ).fetchone()
    assert event is not None
    assert json.loads(event[0]) == {"cause": "base-commit-changed"}


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


def test_self_improvement_records_baseline_and_improvement(
    git_repository: Path,
) -> None:
    write_spec(git_repository, kind="self-improvement")
    git(git_repository, "add", "SPEC.json")
    git(git_repository, "commit", "-m", "request self improvement")
    gate_code = (
        "from pathlib import Path; "
        "raise SystemExit(0 if Path('.git').is_file() else 1)"
    )
    orchestrator = Orchestrator(
        git_repository,
        config_for(
            git_repository,
            gate_exit=0,
            gate_code=gate_code,
        ),
    )

    outcome = orchestrator.reconcile_once()

    assert outcome.status == "succeeded"
    connection = sqlite3.connect(orchestrator.config.state_path)
    rows = connection.execute(
        """
        SELECT kind, payload_json FROM events
        WHERE run_id = ? AND kind IN (
            'baseline_gate_finished',
            'self_improvement_evaluated'
        )
        ORDER BY sequence
        """,
        (outcome.run_id,),
    ).fetchall()
    connection.close()
    assert [row[0] for row in rows] == [
        "baseline_gate_finished",
        "self_improvement_evaluated",
    ]
    evaluation = json.loads(rows[1][1])
    assert evaluation == {
        "baseline_gates": {"result": False},
        "candidate_gates": {"result": True},
        "classification": "improvement",
        "gate_pass_deltas": {"result": 1},
        "passing_gate_count_delta": 1,
    }


def test_self_improvement_does_not_call_an_unchanged_failure_a_regression(
    git_repository: Path,
) -> None:
    write_spec(git_repository, kind="self-improvement")
    git(git_repository, "add", "SPEC.json")
    git(git_repository, "commit", "-m", "request self improvement")
    orchestrator = Orchestrator(
        git_repository,
        config_for(git_repository, gate_exit=1),
    )

    outcome = orchestrator.reconcile_once()

    assert outcome.status == "failed"
    connection = sqlite3.connect(orchestrator.config.state_path)
    row = connection.execute(
        """
        SELECT payload_json FROM events
        WHERE run_id = ? AND kind = 'self_improvement_evaluated'
        """,
        (outcome.run_id,),
    ).fetchone()
    connection.close()
    assert row is not None
    assert json.loads(row[0]) == {
        "baseline_gates": {"result": False},
        "candidate_gates": {"result": False},
        "classification": "no-improvement",
        "failed_gate": "result",
        "gate_pass_deltas": {"result": 0},
    }
