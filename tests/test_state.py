from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import autobuild.state as state_module
from autobuild.models import RunStatus, WorkItem, WorkKind
from autobuild.spec import Specification
from autobuild.state import StaleLeaseError, StateStore


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


def test_claim_is_atomic_and_orders_ready_items(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.db")
    store.initialize()
    desired = specification(("low", 1), ("high", 10))
    store.sync_spec(desired)

    claim = store.claim_next(desired, "base", 60, 3)
    second = store.claim_next(desired, "base", 60, 3)

    assert claim is not None
    assert claim.work_item.id == "high"
    assert second is not None
    assert second.work_item.id == "low"
    assert store.claim_next(desired, "base", 60, 3) is None


def test_stale_generation_cannot_transition(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.db")
    store.initialize()
    desired = specification(("task", 1))
    store.sync_spec(desired)
    claim = store.claim_next(desired, "base", 60, 3)
    assert claim is not None
    stale_claim = replace(claim, generation=claim.generation + 1)

    with pytest.raises(StaleLeaseError):
        store.transition(
            stale_claim,
            RunStatus.LEASED,
            RunStatus.EXECUTING,
        )

    assert store.status()["recent_runs"][0]["status"] == RunStatus.LEASED.value


def test_restart_expires_lease_and_uses_higher_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = datetime(2026, 7, 28, tzinfo=UTC)
    monkeypatch.setattr(state_module, "_now", lambda: clock)
    store = StateStore(tmp_path / "state.db")
    store.initialize()
    desired = specification(("task", 1))
    store.sync_spec(desired)
    first = store.claim_next(desired, "base", 1, 3)
    assert first is not None

    clock += timedelta(seconds=2)
    second = store.claim_next(desired, "base", 60, 3)

    assert second is not None
    assert second.generation == first.generation + 1
    runs = store.status()["recent_runs"]
    assert {run["status"] for run in runs} == {"leased", "stale"}
    with pytest.raises(StaleLeaseError):
        store.record_event(first, "late", {})


def test_active_run_renews_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = datetime(2026, 7, 28, tzinfo=UTC)
    monkeypatch.setattr(state_module, "_now", lambda: clock)
    store = StateStore(tmp_path / "state.db")
    store.initialize()
    desired = specification(("task", 1))
    store.sync_spec(desired)
    claim = store.claim_next(desired, "base", 2, 3)
    assert claim is not None
    store.transition(claim, RunStatus.LEASED, RunStatus.EXECUTING)

    clock += timedelta(seconds=1)
    store.renew_lease(claim, 5)
    clock += timedelta(seconds=2)

    assert store.claim_next(desired, "base", 2, 3) is None
    assert store.status()["recent_runs"][0]["status"] == "executing"


def test_expired_run_cannot_renew_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = datetime(2026, 7, 28, tzinfo=UTC)
    monkeypatch.setattr(state_module, "_now", lambda: clock)
    store = StateStore(tmp_path / "state.db")
    store.initialize()
    desired = specification(("task", 1))
    store.sync_spec(desired)
    claim = store.claim_next(desired, "base", 1, 3)
    assert claim is not None
    clock += timedelta(seconds=2)

    with pytest.raises(StaleLeaseError):
        store.renew_lease(claim, 5)


def test_attempt_limit_marks_item_blocked(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.db")
    store.initialize()
    desired = specification(("task", 1))
    store.sync_spec(desired)
    claim = store.claim_next(desired, "base", 60, 1)
    assert claim is not None
    store.transition(claim, RunStatus.LEASED, RunStatus.FAILED)

    assert store.claim_next(desired, "base", 60, 1) is None
    assert store.status()["work_items"][0]["status"] == "blocked"


def test_sync_marks_removed_item_superseded_and_restores_it(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.db")
    store.initialize()
    initial = specification(("keep", 1), ("remove", 2))
    store.sync_spec(initial)
    store.sync_spec(specification(("keep", 1), digest="spec-b"))
    by_id = {item["id"]: item for item in store.status()["work_items"]}
    assert by_id["remove"]["status"] == "superseded"

    store.sync_spec(specification(("keep", 1), ("remove", 2), digest="spec-c"))
    by_id = {item["id"]: item for item in store.status()["work_items"]}
    assert by_id["remove"]["status"] == "ready"


def test_success_marks_item_achieved(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.db")
    store.initialize()
    desired = specification(("task", 1))
    store.sync_spec(desired)
    claim = store.claim_next(desired, "base", 60, 3)
    assert claim is not None
    store.transition(claim, RunStatus.LEASED, RunStatus.EXECUTING)
    store.transition(claim, RunStatus.EXECUTING, RunStatus.EVALUATING)
    store.transition(claim, RunStatus.EVALUATING, RunStatus.PROMOTING)
    store.transition(claim, RunStatus.PROMOTING, RunStatus.SUCCEEDED)

    assert store.status()["work_items"][0]["status"] == "achieved"

    expanded = specification(("task", 1), ("unrelated", 2), digest="spec-b")
    store.sync_spec(expanded)
    by_id = {item["id"]: item for item in store.status()["work_items"]}
    assert by_id["task"]["status"] == "achieved"
    assert by_id["unrelated"]["status"] == "ready"

    changed = specification(
        ("task", 1),
        ("unrelated", 2),
        digest="spec-c",
        item_digests={"task": "item-task-v2"},
    )
    store.sync_spec(changed)
    by_id = {item["id"]: item for item in store.status()["work_items"]}
    assert by_id["task"]["status"] == "ready"


def test_sync_migrates_legacy_full_spec_digest_without_reopening(
    tmp_path: Path,
) -> None:
    store = StateStore(tmp_path / "state.db")
    store.initialize()
    legacy = specification(
        ("task", 1),
        digest="legacy-full-spec",
        item_digests={"task": "legacy-full-spec"},
    )
    store.sync_spec(legacy)
    with sqlite3.connect(store.path) as connection:
        connection.execute("UPDATE work_items SET status = 'achieved' WHERE id = 'task'")

    migrated = specification(
        ("task", 1),
        digest="legacy-full-spec",
        item_digests={"task": "item-task"},
    )
    store.sync_spec(migrated)

    assert store.status()["work_items"][0]["status"] == "achieved"
    with sqlite3.connect(store.path) as connection:
        stored_digest = connection.execute(
            "SELECT spec_digest FROM work_items WHERE id = 'task'"
        ).fetchone()[0]
    assert stored_digest == "item-task"
