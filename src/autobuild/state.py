"""SQLite event and lease state for resumable execution."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .models import (
    AuthorityLossCause,
    Claim,
    ControllerLease,
    RunStatus,
    WorkItem,
    WorkKind,
)
from .spec import Specification


class StaleLeaseError(RuntimeError):
    """An active run lost desired-state, source, or lease authority."""

    def __init__(
        self,
        message: str,
        cause: AuthorityLossCause = AuthorityLossCause.RUN_NOT_ACTIVE,
    ) -> None:
        super().__init__(message)
        self.cause = cause


class ControllerLeaseError(RuntimeError):
    """A controller does not own the current repository lease."""


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
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            yield connection
            connection.commit()
        except BaseException as error:
            connection.rollback()
            if (
                isinstance(error, sqlite3.OperationalError)
                and getattr(error, "sqlite_errorcode", 0) & 0xFF
                in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}
            ):
                raise ControllerLeaseError(
                    "controller ownership is held by an active operation"
                ) from error
            raise
        finally:
            connection.close()

    @contextmanager
    def _read_only_connect(self) -> Iterator[sqlite3.Connection]:
        uri = f"{self.path.resolve().as_uri()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        try:
            yield connection
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
                CREATE TABLE IF NOT EXISTS controller_lease (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    repository TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    generation INTEGER NOT NULL,
                    lease_expires_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS runs_item_status
                    ON runs(work_item_id, status);
                """
            )

    def acquire_controller_lease(
        self,
        repository: Path,
        lease_seconds: int,
        *,
        owner_id: str,
    ) -> ControllerLease:
        repository_key = os.path.normcase(str(repository.resolve()))
        with self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
            except sqlite3.OperationalError as error:
                if error.sqlite_errorcode == sqlite3.SQLITE_BUSY:
                    raise ControllerLeaseError(
                        "controller ownership is held by an active operation"
                    ) from error
                raise
            now_value = _now()
            now = _timestamp(now_value)
            lease_expires_at = _timestamp(
                now_value + timedelta(seconds=lease_seconds)
            )
            current = connection.execute(
                "SELECT * FROM controller_lease WHERE singleton = 1"
            ).fetchone()
            if (
                current is not None
                and current["lease_expires_at"] > now
                and (
                    current["owner_id"] != owner_id
                    or current["repository"] != repository_key
                )
            ):
                raise ControllerLeaseError(
                    "controller ownership is held by another current owner"
                )
            generation = (
                int(current["generation"])
                if current is not None
                and current["owner_id"] == owner_id
                and current["repository"] == repository_key
                and current["lease_expires_at"] > now
                else int(current["generation"]) + 1
                if current is not None
                else 1
            )
            connection.execute(
                """
                INSERT INTO controller_lease(
                    singleton, repository, owner_id, generation,
                    lease_expires_at, updated_at
                ) VALUES (1, ?, ?, ?, ?, ?)
                ON CONFLICT(singleton) DO UPDATE SET
                    repository = excluded.repository,
                    owner_id = excluded.owner_id,
                    generation = excluded.generation,
                    lease_expires_at = excluded.lease_expires_at,
                    updated_at = excluded.updated_at
                """,
                (
                    repository_key,
                    owner_id,
                    generation,
                    lease_expires_at,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO events(run_id, kind, payload_json, created_at)
                VALUES(NULL, 'controller_acquired', ?, ?)
                """,
                (json.dumps({"generation": generation}), now),
            )
        return ControllerLease(
            owner_id=owner_id,
            generation=generation,
            repository=repository_key,
            lease_expires_at=lease_expires_at,
        )

    def _require_controller_lease(
        self,
        connection: sqlite3.Connection,
        controller_lease: ControllerLease,
        now: str,
    ) -> None:
        current = connection.execute(
            """
            SELECT 1 FROM controller_lease
            WHERE singleton = 1
              AND repository = ?
              AND owner_id = ?
              AND generation = ?
              AND lease_expires_at > ?
            """,
            (
                controller_lease.repository,
                controller_lease.owner_id,
                controller_lease.generation,
                now,
            ),
        ).fetchone()
        if current is None:
            raise ControllerLeaseError(
                f"controller generation {controller_lease.generation} is not current"
            )

    def renew_controller_lease(
        self,
        controller_lease: ControllerLease,
        lease_seconds: int,
    ) -> None:
        now_value = _now()
        now = _timestamp(now_value)
        lease_expires_at = _timestamp(now_value + timedelta(seconds=lease_seconds))
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_controller_lease(connection, controller_lease, now)
            connection.execute(
                """
                UPDATE controller_lease
                SET lease_expires_at = ?, updated_at = ?
                WHERE singleton = 1
                  AND repository = ?
                  AND owner_id = ?
                  AND generation = ?
                """,
                (
                    lease_expires_at,
                    now,
                    controller_lease.repository,
                    controller_lease.owner_id,
                    controller_lease.generation,
                ),
            )

    @contextmanager
    def controller_operation(
        self,
        controller_lease: ControllerLease,
        lease_seconds: int,
    ) -> Iterator[None]:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_controller_lease(
                connection,
                controller_lease,
                _timestamp(),
            )
            yield
            now_value = _now()
            now = _timestamp(now_value)
            connection.execute(
                """
                UPDATE controller_lease
                SET lease_expires_at = ?, updated_at = ?
                WHERE singleton = 1
                  AND repository = ?
                  AND owner_id = ?
                  AND generation = ?
                """,
                (
                    _timestamp(now_value + timedelta(seconds=lease_seconds)),
                    now,
                    controller_lease.repository,
                    controller_lease.owner_id,
                    controller_lease.generation,
                ),
            )

    def release_controller_lease(
        self,
        controller_lease: ControllerLease,
    ) -> bool:
        now = _timestamp()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE controller_lease
                SET lease_expires_at = ?, updated_at = ?
                WHERE singleton = 1
                  AND repository = ?
                  AND owner_id = ?
                  AND generation = ?
                  AND lease_expires_at > ?
                """,
                (
                    now,
                    now,
                    controller_lease.repository,
                    controller_lease.owner_id,
                    controller_lease.generation,
                    now,
                ),
            )
            if cursor.rowcount != 1:
                return False
            connection.execute(
                """
                INSERT INTO events(run_id, kind, payload_json, created_at)
                VALUES(NULL, 'controller_released', ?, ?)
                """,
                (
                    json.dumps({"generation": controller_lease.generation}),
                    now,
                ),
            )
            return True

    def sync_spec(
        self,
        specification: Specification,
        *,
        controller_lease: ControllerLease,
    ) -> None:
        now = _timestamp()
        desired_ids = {item.id for item in specification.work_items}
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_controller_lease(connection, controller_lease, now)
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
                            WHEN work_items.status = 'achieved'
                                 AND work_items.spec_digest = ? THEN 'achieved'
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
                        specification.digest,
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
            connection.execute(
                "INSERT INTO events(run_id, kind, payload_json, created_at) VALUES(?, ?, ?, ?)",
                (
                    row["id"],
                    "authority_lost",
                    json.dumps(
                        {"cause": AuthorityLossCause.LEASE_EXPIRED.value},
                        sort_keys=True,
                    ),
                    now,
                ),
            )

    def claim_next(
        self,
        specification: Specification,
        base_commit: str,
        lease_seconds: int,
        max_attempts: int,
        *,
        controller_lease: ControllerLease,
        kind: WorkKind | None = None,
    ) -> Claim | None:
        now_value = _now()
        now = _timestamp(now_value)
        lease_expires_at = _timestamp(now_value + timedelta(seconds=lease_seconds))
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_controller_lease(connection, controller_lease, now)
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
        controller_lease: ControllerLease,
        detail: str = "",
        worktree: Path | None = None,
    ) -> None:
        now = _timestamp()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_controller_lease(connection, controller_lease, now)
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

    def renew_lease(
        self,
        claim: Claim,
        lease_seconds: int,
        *,
        controller_lease: ControllerLease,
    ) -> None:
        now_value = _now()
        now = _timestamp(now_value)
        lease_expires_at = _timestamp(now_value + timedelta(seconds=lease_seconds))
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_controller_lease(connection, controller_lease, now)
            current = connection.execute(
                """
                SELECT generation, status, lease_expires_at
                FROM runs WHERE id = ?
                """,
                (claim.run_id,),
            ).fetchone()
            if current is None or current["generation"] != claim.generation:
                raise StaleLeaseError(
                    f"run {claim.run_id} generation {claim.generation} cannot renew",
                    AuthorityLossCause.LEASE_GENERATION_CHANGED,
                )
            if current["lease_expires_at"] <= now:
                raise StaleLeaseError(
                    f"run {claim.run_id} generation {claim.generation} expired",
                    AuthorityLossCause.LEASE_EXPIRED,
                )
            if current["status"] not in {
                RunStatus.LEASED.value,
                RunStatus.EXECUTING.value,
                RunStatus.EVALUATING.value,
                RunStatus.PROMOTING.value,
            }:
                raise StaleLeaseError(
                    f"run {claim.run_id} generation {claim.generation} is not active",
                    AuthorityLossCause.RUN_NOT_ACTIVE,
                )
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
                    f"run {claim.run_id} generation {claim.generation} cannot renew",
                    AuthorityLossCause.RUN_NOT_ACTIVE,
                )

    def expire_claim(
        self,
        claim: Claim,
        cause: AuthorityLossCause,
        *,
        controller_lease: ControllerLease,
    ) -> bool:
        now = _timestamp()
        detail = f"authority lost: {cause.value}"
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_controller_lease(connection, controller_lease, now)
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
                    "authority_lost",
                    json.dumps({"cause": cause.value}, sort_keys=True),
                    now,
                ),
            )
            return True

    def record_event(
        self,
        claim: Claim,
        kind: str,
        payload: dict[str, object],
        *,
        controller_lease: ControllerLease,
    ) -> None:
        now = _timestamp()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_controller_lease(connection, controller_lease, now)
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
        *,
        controller_lease: ControllerLease,
    ) -> None:
        now = _timestamp()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_controller_lease(connection, controller_lease, now)
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
        if not self.path.is_file():
            return {
                "controller_lease": None,
                "work_items": [],
                "recent_runs": [],
            }
        with self._read_only_connect() as connection:
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
            try:
                controller = connection.execute(
                    """
                    SELECT generation, lease_expires_at
                    FROM controller_lease WHERE singleton = 1
                    """
                ).fetchone()
            except sqlite3.OperationalError as error:
                if "no such table: controller_lease" not in str(error):
                    raise
                controller = None
            controller_status = None
            if controller is not None:
                controller_status = {
                    **dict(controller),
                    "active": controller["lease_expires_at"] > _timestamp(),
                }
            return {
                "controller_lease": controller_status,
                "work_items": items,
                "recent_runs": runs,
            }
