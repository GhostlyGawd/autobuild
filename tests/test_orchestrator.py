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
from autobuild.config import (
    AgentConfig,
    Config,
    PolicyConfig,
    SelfImprovementConfig,
)
from autobuild.gitops import GitError, current_commit
from autobuild.models import ChangeSurface, Gate
from autobuild.orchestrator import Orchestrator


class InjectedControllerCrash(BaseException):
    """Simulate process death without controller exception finalization."""


def config_for(
    root: Path,
    *,
    gate_exit: int,
    gate_code: str | None = None,
    auto_promote: bool = True,
    lease_seconds: int = 60,
    agent_code: str | None = None,
    max_candidates: int = 1,
    candidate_timeout_seconds: int = 30,
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
        self_improvement=SelfImprovementConfig(
            max_candidates=max_candidates,
            candidate_timeout_seconds=candidate_timeout_seconds,
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


def test_concurrent_controller_defers_during_promotion_transaction(
    git_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_promote = orchestrator_module.promote_fast_forward
    promotion_started = threading.Event()
    allow_promotion = threading.Event()
    first_outcomes = []

    def wait_during_promotion(*args, **kwargs):
        promotion_started.set()
        if not allow_promotion.wait(timeout=15):
            raise AssertionError("second controller did not reach the lock")
        return original_promote(*args, **kwargs)

    monkeypatch.setattr(
        orchestrator_module,
        "promote_fast_forward",
        wait_during_promotion,
    )
    config = config_for(git_repository, gate_exit=0, lease_seconds=10)
    first = Orchestrator(git_repository, config)
    second = Orchestrator(git_repository, config)
    thread = threading.Thread(
        target=lambda: first_outcomes.append(first.reconcile_once()),
        daemon=True,
    )
    thread.start()
    assert promotion_started.wait(timeout=10)

    try:
        second_outcome = second.reconcile_once()
    finally:
        allow_promotion.set()
        thread.join(timeout=10)

    assert second_outcome.status == "deferred"
    assert second_outcome.run_id is None
    assert "active operation" in second_outcome.detail
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
        "candidate_id": "candidate-001",
        "candidate_gates": {"result": True},
        "classification": "improvement",
        "eligible": True,
        "gate_pass_deltas": {"result": 1},
        "passing_gate_count_delta": 1,
        "quality": {
            "changed_files": 1,
            "changed_lines": 1,
            "deletions": 0,
            "insertions": 1,
        },
        "score": 1,
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
        "candidate_id": "candidate-001",
        "candidate_gates": {"result": False},
        "classification": "no-improvement",
        "eligible": False,
        "gate_pass_deltas": {"result": 0},
        "passing_gate_count_delta": 0,
        "quality": {
            "changed_files": 1,
            "changed_lines": 1,
            "deletions": 0,
            "insertions": 1,
        },
        "score": 0,
    }


def test_self_improvement_ranks_candidates_and_promotes_deterministic_winner(
    git_repository: Path,
) -> None:
    write_spec(git_repository, kind="self-improvement")
    git(git_repository, "add", "SPEC.json")
    git(git_repository, "commit", "-m", "request ranked self improvement")
    agent_code = (
        "from pathlib import Path; "
        "candidate = Path.cwd().name.split('-', 1)[0]; "
        "Path('candidate.txt').write_text(candidate + '\\n')"
    )
    gate_code = (
        "from pathlib import Path; "
        "candidate = Path('candidate.txt'); "
        "raise SystemExit(0 if candidate.is_file() "
        "and candidate.read_text().strip() != '003' else 1)"
    )
    orchestrator = Orchestrator(
        git_repository,
        config_for(
            git_repository,
            gate_exit=0,
            gate_code=gate_code,
            agent_code=agent_code,
            max_candidates=3,
        ),
    )

    outcome = orchestrator.reconcile_once()

    assert outcome.status == "succeeded", outcome.detail
    assert (git_repository / "candidate.txt").read_text(encoding="utf-8") == "001\n"
    state = orchestrator.store.status()
    rankings = sorted(state["candidate_rankings"], key=lambda row: row["rank"])
    assert [
        (
            row["candidate_id"],
            row["rank"],
            row["score"],
            row["eligible"],
            row["selected"],
        )
        for row in rankings
    ] == [
        ("candidate-001", 1, 1, True, True),
        ("candidate-002", 2, 1, True, False),
        ("candidate-003", 3, 0, False, False),
    ]
    assert {
        (
            row["changed_files"],
            row["insertions"],
            row["deletions"],
            row["changed_lines"],
        )
        for row in rankings
    } == {(1, 1, 0, 1)}
    assert len({row["worktree"] for row in rankings}) == 3
    assert not Path(rankings[0]["worktree"]).exists()
    assert Path(rankings[1]["worktree"]).exists()
    assert Path(rankings[2]["worktree"]).exists()
    assert state["promotion_decisions"] == [
        {
            "run_id": outcome.run_id,
            "candidate_id": "candidate-001",
            "candidate_commit": rankings[0]["candidate_commit"],
            "decision": "promoted",
            "promoted_commit": rankings[0]["candidate_commit"],
            "updated_at": state["promotion_decisions"][0]["updated_at"],
        }
    ]


def test_self_improvement_ranks_unequal_quality_before_candidate_id(
    git_repository: Path,
) -> None:
    write_spec(git_repository, kind="self-improvement")
    git(git_repository, "add", "SPEC.json")
    git(git_repository, "commit", "-m", "request quality-ranked self improvement")
    agent_code = (
        "from pathlib import Path; "
        "candidate = Path.cwd().name.split('-', 1)[0]; "
        "files = "
        "{'001': {'large.txt': 'a\\nb\\nc\\n'}, "
        "'002': {'first.txt': 'a\\n', 'second.txt': 'b\\n'}, "
        "'003': {'small.txt': 'a\\nb\\n'}}[candidate]; "
        "[Path(name).write_text(content) for name, content in files.items()]"
    )
    orchestrator = Orchestrator(
        git_repository,
        config_for(
            git_repository,
            gate_exit=0,
            agent_code=agent_code,
            max_candidates=3,
        ),
    )

    outcome = orchestrator.reconcile_once()

    assert outcome.status == "succeeded", outcome.detail
    assert (git_repository / "small.txt").read_text(encoding="utf-8") == "a\nb\n"
    rankings = sorted(
        orchestrator.store.status()["candidate_rankings"],
        key=lambda row: row["rank"],
    )
    assert [
        (
            row["candidate_id"],
            row["changed_lines"],
            row["changed_files"],
            row["selected"],
        )
        for row in rankings
    ] == [
        ("candidate-003", 2, 1, True),
        ("candidate-002", 2, 2, False),
        ("candidate-001", 3, 1, False),
    ]


def test_quality_metric_tampering_prevents_ranking_and_promotion(
    git_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_spec(git_repository, kind="self-improvement")
    git(git_repository, "add", "SPEC.json")
    git(git_repository, "commit", "-m", "request measured self improvement")
    monkeypatch.setattr(
        orchestrator_module,
        "measure_change_surface",
        lambda *_arguments: ChangeSurface(1, 1, 0, 2),
    )
    orchestrator = Orchestrator(
        git_repository,
        config_for(git_repository, gate_exit=0),
    )
    base = current_commit(git_repository)

    outcome = orchestrator.reconcile_once()

    assert outcome.status == "failed"
    assert "experiment quality vector is invalid" in outcome.detail
    assert current_commit(git_repository) == base
    state = orchestrator.store.status()
    assert state["candidate_rankings"][0]["changed_lines"] is None
    assert state["candidate_rankings"][0]["rank"] is None
    assert state["promotion_decisions"] == []


def test_self_improvement_candidate_timeout_prevents_promotion(
    git_repository: Path,
) -> None:
    write_spec(git_repository, kind="self-improvement")
    git(git_repository, "add", "SPEC.json")
    git(git_repository, "commit", "-m", "request bounded self improvement")
    orchestrator = Orchestrator(
        git_repository,
        config_for(
            git_repository,
            gate_exit=0,
            agent_code="import time; time.sleep(2)",
            max_candidates=2,
            candidate_timeout_seconds=1,
        ),
    )
    base = current_commit(git_repository)

    outcome = orchestrator.reconcile_once()

    assert outcome.status == "failed"
    assert outcome.detail == "no eligible self-improvement candidate"
    assert current_commit(git_repository) == base
    state = orchestrator.store.status()
    rankings = sorted(state["candidate_rankings"], key=lambda row: row["rank"])
    assert len(rankings) == 2
    assert all(row["classification"] == "timed-out" for row in rankings)
    assert all(row["score"] == 0 and not row["eligible"] for row in rankings)
    assert all(row["gate_results"] == {"result": None} for row in rankings)
    assert [row["candidate_id"] for row in rankings] == [
        "candidate-001",
        "candidate-002",
    ]
    assert state["promotion_decisions"][0]["decision"] == "no-eligible-candidate"
    assert state["promotion_decisions"][0]["candidate_id"] is None


def test_restart_after_crash_before_git_makes_run_retryable(
    git_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = current_commit(git_repository)
    real_promote = orchestrator_module.promote_fast_forward
    orchestrator = Orchestrator(
        git_repository,
        config_for(git_repository, gate_exit=0),
    )

    def crash_before_git(*_arguments: object) -> str:
        raise InjectedControllerCrash

    monkeypatch.setattr(
        orchestrator_module,
        "promote_fast_forward",
        crash_before_git,
    )
    with pytest.raises(InjectedControllerCrash):
        orchestrator.reconcile_once()

    state = orchestrator.store.status()
    assert current_commit(git_repository) == base
    assert state["recent_runs"][0]["status"] == "promoting"
    assert len(state["promotion_intents"]) == 1
    worktree = Path(state["promotion_intents"][0]["worktree"])
    assert worktree.exists()

    monkeypatch.setattr(
        orchestrator_module,
        "promote_fast_forward",
        real_promote,
    )
    recovered = Orchestrator(
        git_repository,
        config_for(git_repository, gate_exit=0),
    ).reconcile_once()

    assert recovered.status == "stale"
    assert recovered.detail == "promotion stopped before Git changed the base"
    assert current_commit(git_repository) == base
    assert worktree.exists()
    state = orchestrator.store.status()
    assert state["recent_runs"][0]["status"] == "stale"
    assert state["work_items"][0]["status"] == "ready"


def test_restart_after_crash_after_git_finalizes_once(
    git_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_spec(git_repository, kind="self-improvement")
    git(git_repository, "add", "SPEC.json")
    git(git_repository, "commit", "-m", "request recoverable promotion")
    real_promote = orchestrator_module.promote_fast_forward
    orchestrator = Orchestrator(
        git_repository,
        config_for(git_repository, gate_exit=0),
    )

    def crash_after_git(*arguments: object) -> str:
        real_promote(*arguments)
        raise InjectedControllerCrash

    monkeypatch.setattr(
        orchestrator_module,
        "promote_fast_forward",
        crash_after_git,
    )
    with pytest.raises(InjectedControllerCrash):
        orchestrator.reconcile_once()

    state = orchestrator.store.status()
    intent = state["promotion_intents"][0]
    candidate = intent["candidate_commit"]
    worktree = Path(intent["worktree"])
    assert current_commit(git_repository) == candidate
    assert state["recent_runs"][0]["status"] == "promoting"
    assert state["promotion_decisions"][0]["decision"] == "selected-for-promotion"

    monkeypatch.setattr(
        orchestrator_module,
        "promote_fast_forward",
        real_promote,
    )
    replacement = Orchestrator(
        git_repository,
        config_for(git_repository, gate_exit=0),
    )
    unrelated = git_repository / "unrelated.txt"
    unrelated.write_text("preserve\n", encoding="utf-8")
    deferred = replacement.reconcile_once()

    assert deferred.status == "deferred"
    assert deferred.run_id is None
    assert current_commit(git_repository) == candidate
    state = replacement.store.status()
    assert state["recent_runs"][0]["status"] == "promoting"
    assert state["promotion_decisions"][0]["decision"] == "selected-for-promotion"

    unrelated.unlink()
    recovered = replacement.reconcile_once()
    restarted = Orchestrator(
        git_repository,
        config_for(git_repository, gate_exit=0),
    ).reconcile_once()

    assert recovered.status == "succeeded"
    assert restarted.status == "idle"
    assert current_commit(git_repository) == candidate
    assert worktree.exists()
    state = replacement.store.status()
    assert state["recent_runs"][0]["status"] == "succeeded"
    assert state["work_items"][0]["status"] == "achieved"
    assert state["promotion_decisions"][0]["decision"] == "promoted"
    assert state["promotion_decisions"][0]["promoted_commit"] == candidate
    with sqlite3.connect(replacement.store.path) as connection:
        recovered_events = connection.execute(
            """
            SELECT COUNT(*) FROM events
            WHERE run_id = ? AND kind = 'promotion_recovered'
            """,
            (recovered.run_id,),
        ).fetchone()[0]
    assert recovered_events == 1


def test_restart_repairs_decision_after_run_success(
    git_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_spec(git_repository, kind="self-improvement")
    git(git_repository, "add", "SPEC.json")
    git(git_repository, "commit", "-m", "request post-success recovery")
    orchestrator = Orchestrator(
        git_repository,
        config_for(git_repository, gate_exit=0),
    )

    def crash_after_success(*_arguments: object, **_keywords: object) -> None:
        raise InjectedControllerCrash

    monkeypatch.setattr(
        orchestrator.store,
        "update_promotion_decision",
        crash_after_success,
    )
    with pytest.raises(InjectedControllerCrash):
        orchestrator.reconcile_once()

    state = orchestrator.store.status()
    candidate = state["promotion_intents"][0]["candidate_commit"]
    assert current_commit(git_repository) == candidate
    assert state["recent_runs"][0]["status"] == "succeeded"
    assert state["promotion_decisions"][0]["decision"] == "selected-for-promotion"

    monkeypatch.undo()
    recovered = Orchestrator(
        git_repository,
        config_for(git_repository, gate_exit=0),
    ).reconcile_once()

    assert recovered.status == "succeeded"
    state = orchestrator.store.status()
    assert state["work_items"][0]["status"] == "achieved"
    assert state["promotion_decisions"][0]["decision"] == "promoted"
    assert state["promotion_decisions"][0]["promoted_commit"] == candidate


def test_restart_refuses_divergent_base_without_overwrite(
    git_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_promote = orchestrator_module.promote_fast_forward
    orchestrator = Orchestrator(
        git_repository,
        config_for(git_repository, gate_exit=0),
    )

    def crash_before_git(*_arguments: object) -> str:
        raise InjectedControllerCrash

    monkeypatch.setattr(
        orchestrator_module,
        "promote_fast_forward",
        crash_before_git,
    )
    with pytest.raises(InjectedControllerCrash):
        orchestrator.reconcile_once()
    intent = orchestrator.store.status()["promotion_intents"][0]
    worktree = Path(intent["worktree"])
    (git_repository / "unrelated.txt").write_text("unrelated\n", encoding="utf-8")
    git(git_repository, "add", "unrelated.txt")
    git(git_repository, "commit", "-m", "move base independently")
    divergent = current_commit(git_repository)

    monkeypatch.setattr(
        orchestrator_module,
        "promote_fast_forward",
        real_promote,
    )
    recovered = Orchestrator(
        git_repository,
        config_for(git_repository, gate_exit=0),
    ).reconcile_once()

    assert recovered.status == "stale"
    assert recovered.detail == "promotion recovery refused a divergent base commit"
    assert current_commit(git_repository) == divergent
    assert current_commit(git_repository) != intent["candidate_commit"]
    assert worktree.exists()


def test_restart_refuses_stale_spec_authority_after_git(
    git_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent_code = (
        "import json; from pathlib import Path; "
        "path = Path('SPEC.json'); data = json.loads(path.read_text()); "
        "data['objective'] = 'Changed candidate authority.'; "
        "path.write_text(json.dumps(data)); "
        "Path('candidate.txt').write_text('candidate\\n')"
    )
    real_promote = orchestrator_module.promote_fast_forward
    orchestrator = Orchestrator(
        git_repository,
        config_for(
            git_repository,
            gate_exit=0,
            agent_code=agent_code,
        ),
    )

    def crash_after_git(*arguments: object) -> str:
        real_promote(*arguments)
        raise InjectedControllerCrash

    monkeypatch.setattr(
        orchestrator_module,
        "promote_fast_forward",
        crash_after_git,
    )
    with pytest.raises(InjectedControllerCrash):
        orchestrator.reconcile_once()
    intent = orchestrator.store.status()["promotion_intents"][0]
    candidate = intent["candidate_commit"]
    assert current_commit(git_repository) == candidate

    monkeypatch.setattr(
        orchestrator_module,
        "promote_fast_forward",
        real_promote,
    )
    recovered = Orchestrator(
        git_repository,
        config_for(git_repository, gate_exit=0),
    ).reconcile_once()

    assert recovered.status == "stale"
    assert recovered.detail == "promotion recovery refused stale SPEC authority"
    assert current_commit(git_repository) == candidate
    state = orchestrator.store.status()
    assert state["work_items"][0]["status"] == "ready"
