"""SQLite event and lease state for resumable execution."""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .models import Claim, RunStatus, WorkItem, WorkKind
from .spec import Specification


class StaleLeaseError(RuntimeError):
    """A worker used a stale or invalid lease generation."""


def _now() -> datetime:
    return datetime.now(UTC)


def _timestamp(value: datetime | None = None) -> str:
    return (value or _now()).isoformat()


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS work_items (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    priority INTEGER NOT NULL,
                    objective TEXT NOT NULL,
                    acceptance_json TEXT NOT NULL,
                    spec_digest TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'ready',
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    work_item_id TEXT NOT NULL REFERENCES work_items(id),
                    generation INTEGER NOT NULL,
                    base_commit TEXT NOT NULL,
                    spec_digest TEXT NOT NULL,
                    status TEXT NOT NULL,
                    lease_expires_at TEXT NOT NULL,
                    worktree TEXT,
                    detail TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT,
                    kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS runs_item_status
                    ON runs(work_item_id, status);
                """
            )

    def sync_spec(self, specification: Specification) -> None:
        now = _timestamp()
        desired_ids = {item.id for item in specification.work_items}
        with self._connect() as connection:
            for item in specification.work_items:
                connection.execute(
                    """
                    INSERT INTO work_items (
                        id, kind, priority, objective, acceptance_json,
                        spec_digest, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        kind = excluded.kind,
                        priority = excluded.priority,
                        objective = excluded.objective,
                        acceptance_json = excluded.acceptance_json,
                        spec_digest = excluded.spec_digest,
                        status = CASE
                            WHEN work_items.status = 'superseded' THEN 'ready'
                            WHEN work_items.spec_digest != excluded.spec_digest
                                 AND work_items.status = 'achieved' THEN 'ready'
                            ELSE work_items.status
                        END,
                        updated_at = excluded.updated_at
                    """,
                    (
                        item.id,
                        item.kind.value,
                        item.priority,
                        item.objective,
                        json.dumps(item.acceptance),
                        item.spec_digest,
                        now,
                    ),
                )
            if desired_ids:
                placeholders = ",".join("?" for _ in desired_ids)
                connection.execute(
                    f"""
                    UPDATE work_items
                    SET status = 'superseded', updated_at = ?
                    WHERE id NOT IN ({placeholders})
                      AND status NOT IN ('active', 'achieved')
                    """,
                    (now, *sorted(desired_ids)),
                )
            connection.execute(
                "INSERT INTO events(run_id, kind, payload_json, created_at) VALUES(NULL, ?, ?, ?)",
                (
                    "spec_observed",
                    json.dumps(
                        {"digest": specification.digest, "items": sorted(desired_ids)},
                        sort_keys=True,
                    ),
                    now,
                ),
            )

    def _expire_leases(self, connection: sqlite3.Connection, now: str) -> None:
        expired = connection.execute(
            """
            SELECT id, work_item_id FROM runs
            WHERE status IN ('leased', 'executing', 'evaluating', 'promoting')
              AND lease_expires_at <= ?
            """,
            (now,),
        ).fetchall()
        for row in expired:
            connection.execute(
                "UPDATE runs SET status = 'stale', detail = ?, updated_at = ? WHERE id = ?",
                ("lease expired", now, row["id"]),
            )
            connection.execute(
                "UPDATE work_items SET status = 'ready', updated_at = ? WHERE id = ?",
                (now, row["work_item_id"]),
            )
            connection.execute(
                "INSERT INTO events(run_id, kind, payload_json, created_at) VALUES(?, ?, ?, ?)",
                (row["id"], "lease_expired", "{}", now),
            )

    def claim_next(
        self,
        specification: Specification,
        base_commit: str,
        lease_seconds: int,
        max_attempts: int,
        *,
        kind: WorkKind | None = None,
    ) -> Claim | None:
        now_value = _now()
        now = _timestamp(now_value)
        lease_expires_at = _timestamp(now_value + timedelta(seconds=lease_seconds))
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._expire_leases(connection, now)
            connection.execute(
                """
                UPDATE work_items
                SET status = 'blocked', updated_at = ?
                WHERE status = 'ready' AND attempt_count >= ?
                """,
                (now, max_attempts),
            )
            query = """
                SELECT * FROM work_items
                WHERE status = 'ready' AND attempt_count < ?
            """
            parameters: list[object] = [max_attempts]
            if kind is not None:
                query += " AND kind = ?"
                parameters.append(kind.value)
            query += " ORDER BY priority DESC, id ASC LIMIT 1"
            row = connection.execute(query, parameters).fetchone()
            if row is None:
                return None

            previous = connection.execute(
                """
                SELECT COALESCE(MAX(generation), 0) AS generation
                FROM runs WHERE work_item_id = ?
                """,
                (row["id"],),
            ).fetchone()
            generation = int(previous["generation"]) + 1
            run_id = str(uuid.uuid4())
            connection.execute(
                """
                INSERT INTO runs(
                    id, work_item_id, generation, base_commit, spec_digest,
                    status, lease_expires_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    row["id"],
                    generation,
                    base_commit,
                    specification.digest,
                    RunStatus.LEASED.value,
                    lease_expires_at,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                UPDATE work_items
                SET status = 'active', attempt_count = attempt_count + 1, updated_at = ?
                WHERE id = ?
                """,
                (now, row["id"]),
            )
            connection.execute(
                "INSERT INTO events(run_id, kind, payload_json, created_at) VALUES(?, ?, ?, ?)",
                (
                    run_id,
                    "claimed",
                    json.dumps({"generation": generation, "base_commit": base_commit}),
                    now,
                ),
            )
            item = WorkItem(
                id=row["id"],
                kind=WorkKind(row["kind"]),
                priority=row["priority"],
                objective=row["objective"],
                acceptance=tuple(json.loads(row["acceptance_json"])),
                spec_digest=row["spec_digest"],
            )
            return Claim(
                run_id=run_id,
                work_item=item,
                generation=generation,
                base_commit=base_commit,
                spec_digest=specification.digest,
                lease_expires_at=lease_expires_at,
            )

    def transition(
        self,
        claim: Claim,
        expected: RunStatus,
        target: RunStatus,
        *,
        detail: str = "",
        worktree: Path | None = None,
    ) -> None:
        now = _timestamp()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE runs
                SET status = ?, detail = ?, worktree = COALESCE(?, worktree), updated_at = ?
                WHERE id = ? AND generation = ? AND status = ?
                  AND lease_expires_at > ?
                """,
                (
                    target.value,
                    detail,
                    str(worktree) if worktree else None,
                    now,
                    claim.run_id,
                    claim.generation,
                    expected.value,
                    now,
                ),
            )
            if cursor.rowcount != 1:
                raise StaleLeaseError(
                    f"run {claim.run_id} generation {claim.generation} is not current"
                )
            connection.execute(
                "INSERT INTO events(run_id, kind, payload_json, created_at) VALUES(?, ?, ?, ?)",
                (
                    claim.run_id,
                    "transition",
                    json.dumps(
                        {"from": expected.value, "to": target.value, "detail": detail},
                        sort_keys=True,
                    ),
                    now,
                ),
            )
            if target is RunStatus.SUCCEEDED:
                connection.execute(
                    "UPDATE work_items SET status = 'achieved', updated_at = ? WHERE id = ?",
                    (now, claim.work_item.id),
                )
            elif target is RunStatus.AWAITING_PROMOTION:
                connection.execute(
                    "UPDATE work_items SET status = 'blocked', updated_at = ? WHERE id = ?",
                    (now, claim.work_item.id),
                )
            elif target in {RunStatus.FAILED, RunStatus.STALE}:
                connection.execute(
                    "UPDATE work_items SET status = 'ready', updated_at = ? WHERE id = ?",
                    (now, claim.work_item.id),
                )

    def renew_lease(self, claim: Claim, lease_seconds: int) -> None:
        now_value = _now()
        now = _timestamp(now_value)
        lease_expires_at = _timestamp(now_value + timedelta(seconds=lease_seconds))
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE runs
                SET lease_expires_at = ?, updated_at = ?
                WHERE id = ? AND generation = ? AND lease_expires_at > ?
                  AND status IN ('leased', 'executing', 'evaluating', 'promoting')
                """,
                (
                    lease_expires_at,
                    now,
                    claim.run_id,
                    claim.generation,
                    now,
                ),
            )
            if cursor.rowcount != 1:
                raise StaleLeaseError(
                    f"run {claim.run_id} generation {claim.generation} cannot renew"
                )

    def expire_claim(self, claim: Claim, detail: str) -> bool:
        now = _timestamp()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE runs
                SET status = 'stale', detail = ?, updated_at = ?
                WHERE id = ? AND generation = ?
                  AND status IN ('leased', 'executing', 'evaluating', 'promoting')
                """,
                (detail, now, claim.run_id, claim.generation),
            )
            if cursor.rowcount != 1:
                return False
            connection.execute(
                "UPDATE work_items SET status = 'ready', updated_at = ? WHERE id = ?",
                (now, claim.work_item.id),
            )
            connection.execute(
                "INSERT INTO events(run_id, kind, payload_json, created_at) VALUES(?, ?, ?, ?)",
                (
                    claim.run_id,
                    "lease_lost",
                    json.dumps({"detail": detail}),
                    now,
                ),
            )
            return True

    def record_event(self, claim: Claim, kind: str, payload: dict[str, object]) -> None:
        now = _timestamp()
        with self._connect() as connection:
            current = connection.execute(
                """
                SELECT 1 FROM runs
                WHERE id = ? AND generation = ? AND lease_expires_at > ?
                  AND status IN ('leased', 'executing', 'evaluating', 'promoting')
                """,
                (claim.run_id, claim.generation, now),
            ).fetchone()
            if current is None:
                raise StaleLeaseError(
                    f"run {claim.run_id} generation {claim.generation} is not current"
                )
            connection.execute(
                "INSERT INTO events(run_id, kind, payload_json, created_at) VALUES(?, ?, ?, ?)",
                (claim.run_id, kind, json.dumps(payload, sort_keys=True), now),
            )

    def record_terminal_event(
        self,
        claim: Claim,
        kind: str,
        payload: dict[str, object],
    ) -> None:
        now = _timestamp()
        with self._connect() as connection:
            current = connection.execute(
                """
                SELECT 1 FROM runs
                WHERE id = ? AND generation = ?
                  AND status IN ('awaiting-promotion', 'succeeded', 'failed', 'stale')
                """,
                (claim.run_id, claim.generation),
            ).fetchone()
            if current is None:
                raise StaleLeaseError(
                    f"run {claim.run_id} generation {claim.generation} is not terminal"
                )
            connection.execute(
                "INSERT INTO events(run_id, kind, payload_json, created_at) VALUES(?, ?, ?, ?)",
                (claim.run_id, kind, json.dumps(payload, sort_keys=True), now),
            )

    def status(self) -> dict[str, object]:
        self.initialize()
        with self._connect() as connection:
            items = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT id, kind, priority, status, attempt_count, updated_at
                    FROM work_items ORDER BY priority DESC, id
                    """
                )
            ]
            runs = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT id, work_item_id, generation, status, base_commit,
                           lease_expires_at, detail, updated_at
                    FROM runs ORDER BY created_at DESC LIMIT 20
                    """
                )
            ]
            return {"work_items": items, "recent_runs": runs}
