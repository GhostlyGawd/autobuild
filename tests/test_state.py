from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import autobuild.state as state_module
from autobuild.models import (
    AuthorityLossCause,
    ChangeSurface,
    ControllerLease,
    RunStatus,
    WorkItem,
    WorkKind,
)
from autobuild.spec import Specification
from autobuild.state import ControllerLeaseError, StaleLeaseError, StateStore


def specification(
    *items: tuple[str, int],
    digest: str = "spec-a",
    item_digests: dict[str, str] | None = None,
) -> Specification:
    item_digests = item_digests or {}
    work_items = tuple(
        WorkItem(
            id=item_id,
            kind=WorkKind.PRODUCT,
            priority=priority,
            objective=f"Complete {item_id}.",
            acceptance=("The item is complete.",),
            spec_digest=item_digests.get(item_id, f"item-{item_id}"),
        )
        for item_id, priority in items
    )
    return Specification(objective="Complete the work.", digest=digest, work_items=work_items)


def owned_store(tmp_path: Path) -> tuple[StateStore, ControllerLease]:
    store = StateStore(tmp_path / "state.db")
    store.initialize()
    controller = store.acquire_controller_lease(
        tmp_path,
        60,
        owner_id="test-controller",
    )
    return store, controller


def test_claim_is_atomic_and_orders_ready_items(tmp_path: Path) -> None:
    store, controller = owned_store(tmp_path)
    desired = specification(("low", 1), ("high", 10))
    store.sync_spec(desired, controller_lease=controller)

    claim = store.claim_next(
        desired, "base", 60, 3, controller_lease=controller
    )
    second = store.claim_next(
        desired, "base", 60, 3, controller_lease=controller
    )

    assert claim is not None
    assert claim.work_item.id == "high"
    assert second is not None
    assert second.work_item.id == "low"
    assert (
        store.claim_next(
            desired, "base", 60, 3, controller_lease=controller
        )
        is None
    )


def test_stale_generation_cannot_transition(tmp_path: Path) -> None:
    store, controller = owned_store(tmp_path)
    desired = specification(("task", 1))
    store.sync_spec(desired, controller_lease=controller)
    claim = store.claim_next(
        desired, "base", 60, 3, controller_lease=controller
    )
    assert claim is not None
    stale_claim = replace(claim, generation=claim.generation + 1)

    with pytest.raises(StaleLeaseError):
        store.transition(
            stale_claim,
            RunStatus.LEASED,
            RunStatus.EXECUTING,
            controller_lease=controller,
        )
    with pytest.raises(StaleLeaseError) as error:
        store.renew_lease(
            stale_claim,
            60,
            controller_lease=controller,
        )

    assert error.value.cause is AuthorityLossCause.LEASE_GENERATION_CHANGED
    assert store.status()["recent_runs"][0]["status"] == RunStatus.LEASED.value


def test_stale_generation_cannot_change_experiment_evidence(
    tmp_path: Path,
) -> None:
    store, controller = owned_store(tmp_path)
    desired = specification(("task", 1))
    store.sync_spec(desired, controller_lease=controller)
    claim = store.claim_next(
        desired, "base", 60, 3, controller_lease=controller
    )
    assert claim is not None
    store.transition(
        claim,
        RunStatus.LEASED,
        RunStatus.EXECUTING,
        controller_lease=controller,
    )
    stale_claim = replace(claim, generation=claim.generation + 1)

    with pytest.raises(StaleLeaseError):
        store.record_experiment_candidate(
            stale_claim,
            candidate_id="candidate-001",
            ordinal=1,
            worktree=tmp_path / "candidate",
            candidate_commit="candidate",
            status="evaluated",
            classification="non-regression",
            gate_results={"test": True},
            score=1,
            all_pass=True,
            non_regressing=True,
            eligible=True,
            quality=ChangeSurface(1, 1, 0, 1),
            controller_lease=controller,
        )

    assert store.status()["candidate_rankings"] == []


def test_sqlite_rejects_quality_metric_tampering(tmp_path: Path) -> None:
    store, controller = owned_store(tmp_path)
    desired = specification(("task", 1))
    store.sync_spec(desired, controller_lease=controller)
    claim = store.claim_next(
        desired, "base", 60, 3, controller_lease=controller
    )
    assert claim is not None
    store.transition(
        claim,
        RunStatus.LEASED,
        RunStatus.EXECUTING,
        controller_lease=controller,
    )

    with pytest.raises(ValueError, match="quality vector is invalid"):
        store.record_experiment_candidate(
            claim,
            candidate_id="candidate-001",
            ordinal=1,
            worktree=tmp_path / "candidate",
            candidate_commit="candidate",
            status="evaluated",
            classification="non-regression",
            gate_results={"test": True},
            score=1,
            all_pass=True,
            non_regressing=True,
            eligible=True,
            quality=ChangeSurface(1, 1, 0, 2),
            controller_lease=controller,
        )

    store.record_experiment_candidate(
        claim,
        candidate_id="candidate-001",
        ordinal=1,
        worktree=tmp_path / "candidate",
        candidate_commit="candidate",
        status="evaluated",
        classification="non-regression",
        gate_results={"test": True},
        score=1,
        all_pass=True,
        non_regressing=True,
        eligible=True,
        quality=ChangeSurface(1, 1, 0, 1),
        controller_lease=controller,
    )
    store.record_experiment_candidate(
        claim,
        candidate_id="candidate-002",
        ordinal=2,
        worktree=tmp_path / "candidate-002",
        candidate_commit="candidate-002",
        status="evaluated",
        classification="non-regression",
        gate_results={"test": True},
        score=1,
        all_pass=True,
        non_regressing=True,
        eligible=True,
        quality=ChangeSurface(1, 2, 0, 2),
        controller_lease=controller,
    )
    store.transition(
        claim,
        RunStatus.EXECUTING,
        RunStatus.EVALUATING,
        controller_lease=controller,
    )
    with pytest.raises(ValueError, match="ranking is not deterministic"):
        store.record_experiment_ranking(
            claim,
            ["candidate-002", "candidate-001"],
            "candidate-002",
            controller_lease=controller,
        )
    store.record_experiment_ranking(
        claim,
        ["candidate-001", "candidate-002"],
        "candidate-001",
        controller_lease=controller,
    )
    connection = sqlite3.connect(store.path)
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            UPDATE experiment_quality
            SET changed_files = 2
            WHERE run_id = ? AND candidate_id = 'candidate-001'
            """,
            (claim.run_id,),
        )
    connection.close()

    candidate = next(
        row
        for row in store.status()["candidate_rankings"]
        if row["candidate_id"] == "candidate-001"
    )
    assert (
        candidate["changed_files"],
        candidate["insertions"],
        candidate["deletions"],
        candidate["changed_lines"],
    ) == (1, 1, 0, 1)


def test_restart_expires_lease_and_uses_higher_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = datetime(2026, 7, 28, tzinfo=UTC)
    monkeypatch.setattr(state_module, "_now", lambda: clock)
    store, controller = owned_store(tmp_path)
    desired = specification(("task", 1))
    store.sync_spec(desired, controller_lease=controller)
    first = store.claim_next(
        desired, "base", 1, 3, controller_lease=controller
    )
    assert first is not None

    clock += timedelta(seconds=2)
    second = store.claim_next(
        desired, "base", 60, 3, controller_lease=controller
    )

    assert second is not None
    assert second.generation == first.generation + 1
    runs = store.status()["recent_runs"]
    assert {run["status"] for run in runs} == {"leased", "stale"}
    with sqlite3.connect(store.path) as connection:
        event = connection.execute(
            """
            SELECT payload_json FROM events
            WHERE run_id = ? AND kind = 'authority_lost'
            """,
            (first.run_id,),
        ).fetchone()
    assert event is not None
    assert json.loads(event[0]) == {"cause": "lease-expired"}
    with pytest.raises(StaleLeaseError):
        store.record_event(
            first,
            "late",
            {},
            controller_lease=controller,
        )


def test_active_run_renews_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = datetime(2026, 7, 28, tzinfo=UTC)
    monkeypatch.setattr(state_module, "_now", lambda: clock)
    store, controller = owned_store(tmp_path)
    desired = specification(("task", 1))
    store.sync_spec(desired, controller_lease=controller)
    claim = store.claim_next(
        desired, "base", 2, 3, controller_lease=controller
    )
    assert claim is not None
    store.transition(
        claim,
        RunStatus.LEASED,
        RunStatus.EXECUTING,
        controller_lease=controller,
    )

    clock += timedelta(seconds=1)
    store.renew_lease(claim, 5, controller_lease=controller)
    clock += timedelta(seconds=2)

    assert (
        store.claim_next(
            desired, "base", 2, 3, controller_lease=controller
        )
        is None
    )
    assert store.status()["recent_runs"][0]["status"] == "executing"


def test_expired_run_cannot_renew_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = datetime(2026, 7, 28, tzinfo=UTC)
    monkeypatch.setattr(state_module, "_now", lambda: clock)
    store, controller = owned_store(tmp_path)
    desired = specification(("task", 1))
    store.sync_spec(desired, controller_lease=controller)
    claim = store.claim_next(
        desired, "base", 1, 3, controller_lease=controller
    )
    assert claim is not None
    clock += timedelta(seconds=2)

    with pytest.raises(StaleLeaseError) as error:
        store.renew_lease(claim, 5, controller_lease=controller)

    assert error.value.cause is AuthorityLossCause.LEASE_EXPIRED


def test_attempt_limit_marks_item_blocked(tmp_path: Path) -> None:
    store, controller = owned_store(tmp_path)
    desired = specification(("task", 1))
    store.sync_spec(desired, controller_lease=controller)
    claim = store.claim_next(
        desired, "base", 60, 1, controller_lease=controller
    )
    assert claim is not None
    store.transition(
        claim,
        RunStatus.LEASED,
        RunStatus.FAILED,
        controller_lease=controller,
    )

    assert (
        store.claim_next(
            desired, "base", 60, 1, controller_lease=controller
        )
        is None
    )
    assert store.status()["work_items"][0]["status"] == "blocked"


def test_sync_marks_removed_item_superseded_and_restores_it(tmp_path: Path) -> None:
    store, controller = owned_store(tmp_path)
    initial = specification(("keep", 1), ("remove", 2))
    store.sync_spec(initial, controller_lease=controller)
    store.sync_spec(
        specification(("keep", 1), digest="spec-b"),
        controller_lease=controller,
    )
    by_id = {item["id"]: item for item in store.status()["work_items"]}
    assert by_id["remove"]["status"] == "superseded"

    store.sync_spec(
        specification(("keep", 1), ("remove", 2), digest="spec-c"),
        controller_lease=controller,
    )
    by_id = {item["id"]: item for item in store.status()["work_items"]}
    assert by_id["remove"]["status"] == "ready"


def test_success_marks_item_achieved(tmp_path: Path) -> None:
    store, controller = owned_store(tmp_path)
    desired = specification(("task", 1))
    store.sync_spec(desired, controller_lease=controller)
    claim = store.claim_next(
        desired, "base", 60, 3, controller_lease=controller
    )
    assert claim is not None
    store.transition(
        claim,
        RunStatus.LEASED,
        RunStatus.EXECUTING,
        controller_lease=controller,
    )
    store.transition(
        claim,
        RunStatus.EXECUTING,
        RunStatus.EVALUATING,
        controller_lease=controller,
    )
    store.transition(
        claim,
        RunStatus.EVALUATING,
        RunStatus.PROMOTING,
        controller_lease=controller,
    )
    store.transition(
        claim,
        RunStatus.PROMOTING,
        RunStatus.SUCCEEDED,
        controller_lease=controller,
    )

    assert store.status()["work_items"][0]["status"] == "achieved"

    expanded = specification(("task", 1), ("unrelated", 2), digest="spec-b")
    store.sync_spec(expanded, controller_lease=controller)
    by_id = {item["id"]: item for item in store.status()["work_items"]}
    assert by_id["task"]["status"] == "achieved"
    assert by_id["unrelated"]["status"] == "ready"

    changed = specification(
        ("task", 1),
        ("unrelated", 2),
        digest="spec-c",
        item_digests={"task": "item-task-v2"},
    )
    store.sync_spec(changed, controller_lease=controller)
    by_id = {item["id"]: item for item in store.status()["work_items"]}
    assert by_id["task"]["status"] == "ready"


def test_sync_migrates_legacy_full_spec_digest_without_reopening(
    tmp_path: Path,
) -> None:
    store, controller = owned_store(tmp_path)
    legacy = specification(
        ("task", 1),
        digest="legacy-full-spec",
        item_digests={"task": "legacy-full-spec"},
    )
    store.sync_spec(legacy, controller_lease=controller)
    with sqlite3.connect(store.path) as connection:
        connection.execute("UPDATE work_items SET status = 'achieved' WHERE id = 'task'")

    migrated = specification(
        ("task", 1),
        digest="legacy-full-spec",
        item_digests={"task": "item-task"},
    )
    store.sync_spec(migrated, controller_lease=controller)

    assert store.status()["work_items"][0]["status"] == "achieved"
    with sqlite3.connect(store.path) as connection:
        stored_digest = connection.execute(
            "SELECT spec_digest FROM work_items WHERE id = 'task'"
        ).fetchone()[0]
    assert stored_digest == "item-task"


def test_controller_lease_is_exclusive_and_recovers_after_expiry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = datetime(2026, 7, 28, tzinfo=UTC)
    monkeypatch.setattr(state_module, "_now", lambda: clock)
    first_store = StateStore(tmp_path / "state.db")
    second_store = StateStore(tmp_path / "state.db")
    first_store.initialize()
    first = first_store.acquire_controller_lease(
        tmp_path,
        2,
        owner_id="first-controller",
    )

    with pytest.raises(ControllerLeaseError):
        second_store.acquire_controller_lease(
            tmp_path,
            2,
            owner_id="second-controller",
        )

    assert second_store.status()["controller_lease"]["active"] is True
    clock += timedelta(seconds=3)
    second = second_store.acquire_controller_lease(
        tmp_path,
        2,
        owner_id="second-controller",
    )

    assert second.generation == first.generation + 1
    with pytest.raises(ControllerLeaseError):
        first_store.renew_controller_lease(first, 2)


def test_status_does_not_create_or_require_controller_ownership(
    tmp_path: Path,
) -> None:
    store = StateStore(tmp_path / "state.db")

    assert store.status() == {
        "controller_lease": None,
        "work_items": [],
        "recent_runs": [],
        "candidate_rankings": [],
        "promotion_decisions": [],
        "promotion_intents": [],
    }
    assert not store.path.exists()


def test_status_reads_state_without_experiment_tables(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.db")
    with sqlite3.connect(store.path) as connection:
        connection.executescript(
            """
            CREATE TABLE work_items (
                id TEXT, kind TEXT, priority INTEGER, status TEXT,
                attempt_count INTEGER, updated_at TEXT
            );
            CREATE TABLE runs (
                id TEXT, work_item_id TEXT, generation INTEGER,
                status TEXT, base_commit TEXT, lease_expires_at TEXT,
                detail TEXT, updated_at TEXT, created_at TEXT
            );
            """
        )

    status = store.status()

    assert status["controller_lease"] is None
    assert status["candidate_rankings"] == []
    assert status["promotion_decisions"] == []
    assert status["promotion_intents"] == []


def test_status_preserves_legacy_experiment_evidence_before_migration(
    tmp_path: Path,
) -> None:
    store, controller = owned_store(tmp_path)
    desired = specification(("task", 1))
    store.sync_spec(desired, controller_lease=controller)
    claim = store.claim_next(
        desired, "base", 60, 3, controller_lease=controller
    )
    assert claim is not None
    store.transition(
        claim,
        RunStatus.LEASED,
        RunStatus.EXECUTING,
        controller_lease=controller,
    )
    store.record_experiment_candidate(
        claim,
        candidate_id="candidate-001",
        ordinal=1,
        worktree=tmp_path / "candidate",
        candidate_commit="candidate",
        status="evaluated",
        classification="non-regression",
        gate_results={"test": True},
        score=1,
        all_pass=True,
        non_regressing=True,
        eligible=True,
        quality=ChangeSurface(1, 1, 0, 1),
        controller_lease=controller,
    )
    store.transition(
        claim,
        RunStatus.EXECUTING,
        RunStatus.EVALUATING,
        controller_lease=controller,
    )
    store.record_experiment_ranking(
        claim,
        ["candidate-001"],
        "candidate-001",
        controller_lease=controller,
    )
    with sqlite3.connect(store.path) as connection:
        connection.execute("DROP TRIGGER experiment_quality_no_update")
        connection.execute("DROP TRIGGER experiment_quality_no_delete")
        connection.execute("DROP TABLE experiment_quality")

    status = store.status()

    assert len(status["candidate_rankings"]) == 1
    candidate = status["candidate_rankings"][0]
    assert candidate["candidate_id"] == "candidate-001"
    assert candidate["selected"] is True
    assert candidate["rank"] == 1
    assert candidate["changed_files"] is None
    assert candidate["changed_lines"] is None
    assert status["promotion_decisions"][0]["candidate_id"] == "candidate-001"
    with sqlite3.connect(store.path) as connection:
        assert (
            connection.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type = 'table' AND name = 'experiment_quality'
                """
            ).fetchone()
            is None
        )


def test_controller_lease_renews_and_fences_state_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = datetime(2026, 7, 28, tzinfo=UTC)
    monkeypatch.setattr(state_module, "_now", lambda: clock)
    store = StateStore(tmp_path / "state.db")
    store.initialize()
    first = store.acquire_controller_lease(
        tmp_path,
        2,
        owner_id="first-controller",
    )
    clock += timedelta(seconds=1)
    store.renew_controller_lease(first, 3)
    desired = specification(("task", 1))
    store.sync_spec(desired, controller_lease=first)

    clock += timedelta(seconds=2)
    claim = store.claim_next(
        desired,
        "base",
        2,
        3,
        controller_lease=first,
    )

    assert claim is not None
    clock += timedelta(seconds=2)
    second = store.acquire_controller_lease(
        tmp_path,
        2,
        owner_id="second-controller",
    )
    with pytest.raises(ControllerLeaseError):
        store.transition(
            claim,
            RunStatus.LEASED,
            RunStatus.PROMOTING,
            controller_lease=first,
        )
    with (
        pytest.raises(ControllerLeaseError),
        store.controller_operation(first, 2),
    ):
        pass
    with store.controller_operation(second, 2):
        pass


def test_promotion_intent_is_immutable_and_stale_controller_cannot_recover(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = datetime(2026, 7, 28, tzinfo=UTC)
    monkeypatch.setattr(state_module, "_now", lambda: clock)
    store, controller = owned_store(tmp_path)
    desired = specification(("task", 1))
    store.sync_spec(desired, controller_lease=controller)
    claim = store.claim_next(
        desired, "base", 60, 3, controller_lease=controller
    )
    assert claim is not None
    worktree = tmp_path / "candidate"
    store.transition(
        claim,
        RunStatus.LEASED,
        RunStatus.EXECUTING,
        controller_lease=controller,
        worktree=worktree,
    )
    store.transition(
        claim,
        RunStatus.EXECUTING,
        RunStatus.EVALUATING,
        controller_lease=controller,
    )
    store.transition(
        claim,
        RunStatus.EVALUATING,
        RunStatus.PROMOTING,
        controller_lease=controller,
    )
    store.record_promotion_intent(
        claim,
        "candidate",
        worktree,
        controller_lease=controller,
    )
    intent = store.status()["promotion_intents"][0]
    assert {
        "run_id": intent["run_id"],
        "generation": intent["generation"],
        "expected_base": intent["expected_base"],
        "candidate_commit": intent["candidate_commit"],
        "worktree": intent["worktree"],
        "spec_digest": intent["spec_digest"],
        "work_item_spec_digest": intent["work_item_spec_digest"],
    } == {
        "run_id": claim.run_id,
        "generation": claim.generation,
        "expected_base": claim.base_commit,
        "candidate_commit": "candidate",
        "worktree": str(worktree),
        "spec_digest": claim.spec_digest,
        "work_item_spec_digest": claim.work_item.spec_digest,
    }

    with (
        sqlite3.connect(store.path) as connection,
        pytest.raises(sqlite3.IntegrityError, match="immutable"),
    ):
        connection.execute(
            """
            UPDATE promotion_intents
            SET candidate_commit = 'replacement'
            WHERE run_id = ?
            """,
            (claim.run_id,),
        )
    with (
        sqlite3.connect(store.path) as connection,
        pytest.raises(sqlite3.IntegrityError, match="immutable"),
    ):
        connection.execute(
            "DELETE FROM promotion_intents WHERE run_id = ?",
            (claim.run_id,),
        )

    clock += timedelta(seconds=61)
    replacement = store.acquire_controller_lease(
        tmp_path,
        60,
        owner_id="replacement-controller",
    )
    with pytest.raises(ControllerLeaseError):
        store.recover_promotion(
            desired,
            "candidate",
            controller_lease=controller,
        )

    recovered = store.recover_promotion(
        desired,
        "candidate",
        controller_lease=replacement,
    )

    assert recovered is not None
    assert recovered.status == "succeeded"
    assert store.status()["recent_runs"][0]["status"] == "succeeded"
