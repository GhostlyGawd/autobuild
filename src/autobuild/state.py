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
    ChangeSurface,
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
                CREATE TABLE IF NOT EXISTS experiment_candidates (
                    run_id TEXT NOT NULL REFERENCES runs(id),
                    candidate_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    worktree TEXT NOT NULL,
                    base_commit TEXT NOT NULL,
                    candidate_commit TEXT,
                    status TEXT NOT NULL,
                    classification TEXT NOT NULL,
                    gate_results_json TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    all_pass INTEGER NOT NULL,
                    non_regressing INTEGER NOT NULL,
                    eligible INTEGER NOT NULL,
                    rank INTEGER,
                    selected INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (run_id, candidate_id)
                );
                CREATE TABLE IF NOT EXISTS promotion_decisions (
                    run_id TEXT PRIMARY KEY REFERENCES runs(id),
                    candidate_id TEXT,
                    candidate_commit TEXT,
                    decision TEXT NOT NULL,
                    promoted_commit TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS experiment_quality (
                    run_id TEXT NOT NULL,
                    candidate_id TEXT NOT NULL,
                    changed_files INTEGER NOT NULL CHECK (changed_files >= 0),
                    insertions INTEGER NOT NULL CHECK (insertions >= 0),
                    deletions INTEGER NOT NULL CHECK (deletions >= 0),
                    changed_lines INTEGER NOT NULL CHECK (
                        changed_lines >= 0
                        AND changed_lines = insertions + deletions
                    ),
                    PRIMARY KEY (run_id, candidate_id),
                    FOREIGN KEY (run_id, candidate_id)
                        REFERENCES experiment_candidates(run_id, candidate_id)
                );
                CREATE INDEX IF NOT EXISTS runs_item_status
                    ON runs(work_item_id, status);
                CREATE INDEX IF NOT EXISTS experiment_candidates_rank
                    ON experiment_candidates(run_id, rank);
                CREATE UNIQUE INDEX IF NOT EXISTS experiment_candidates_one_selected
                    ON experiment_candidates(run_id) WHERE selected = 1;
                CREATE TRIGGER IF NOT EXISTS experiment_quality_no_update
                BEFORE UPDATE ON experiment_quality
                BEGIN
                    SELECT RAISE(ABORT, 'experiment quality is immutable');
                END;
                CREATE TRIGGER IF NOT EXISTS experiment_quality_no_delete
                BEFORE DELETE ON experiment_quality
                BEGIN
                    SELECT RAISE(ABORT, 'experiment quality is immutable');
                END;
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

    def record_experiment_candidate(
        self,
        claim: Claim,
        *,
        candidate_id: str,
        ordinal: int,
        worktree: Path,
        candidate_commit: str | None,
        status: str,
        classification: str,
        gate_results: dict[str, bool | None],
        score: int,
        all_pass: bool,
        non_regressing: bool,
        eligible: bool,
        quality: ChangeSurface | None,
        controller_lease: ControllerLease,
    ) -> None:
        expected_score = sum(result is True for result in gate_results.values())
        expected_all_pass = bool(gate_results) and all(
            result is True for result in gate_results.values()
        )
        if score != expected_score or all_pass != expected_all_pass:
            raise ValueError("experiment score does not match its gate results")
        if quality is not None and (
            min(
                quality.changed_files,
                quality.insertions,
                quality.deletions,
                quality.changed_lines,
            )
            < 0
            or quality.changed_lines != quality.insertions + quality.deletions
        ):
            raise ValueError("experiment quality vector is invalid")
        if quality is not None and candidate_commit is None:
            raise ValueError("experiment quality requires a candidate commit")
        if status == "evaluated" and quality is None:
            raise ValueError("evaluated experiment requires a quality vector")
        if eligible and not (
            all_pass
            and non_regressing
            and candidate_commit
            and quality is not None
            and status == "evaluated"
            and classification in {"improvement", "non-regression"}
        ):
            raise ValueError("experiment candidate is not eligible")
        now = _timestamp()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_controller_lease(connection, controller_lease, now)
            current = connection.execute(
                """
                SELECT 1 FROM runs
                WHERE id = ? AND generation = ? AND lease_expires_at > ?
                  AND status IN ('executing', 'evaluating')
                """,
                (claim.run_id, claim.generation, now),
            ).fetchone()
            if current is None:
                raise StaleLeaseError(
                    f"run {claim.run_id} generation {claim.generation} is not current"
                )
            existing = connection.execute(
                """
                SELECT candidate_commit
                FROM experiment_candidates
                WHERE run_id = ? AND candidate_id = ?
                """,
                (claim.run_id, candidate_id),
            ).fetchone()
            if (
                existing is not None
                and existing["candidate_commit"] is not None
                and existing["candidate_commit"] != candidate_commit
            ):
                raise ValueError("experiment candidate commit is immutable")
            connection.execute(
                """
                INSERT INTO experiment_candidates(
                    run_id, candidate_id, ordinal, worktree, base_commit,
                    candidate_commit, status, classification, gate_results_json,
                    score, all_pass, non_regressing, eligible, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, candidate_id) DO UPDATE SET
                    worktree = excluded.worktree,
                    candidate_commit = excluded.candidate_commit,
                    status = excluded.status,
                    classification = excluded.classification,
                    gate_results_json = excluded.gate_results_json,
                    score = excluded.score,
                    all_pass = excluded.all_pass,
                    non_regressing = excluded.non_regressing,
                    eligible = excluded.eligible,
                    updated_at = excluded.updated_at
                """,
                (
                    claim.run_id,
                    candidate_id,
                    ordinal,
                    str(worktree),
                    claim.base_commit,
                    candidate_commit,
                    status,
                    classification,
                    json.dumps(gate_results, sort_keys=True),
                    score,
                    int(all_pass),
                    int(non_regressing),
                    int(eligible),
                    now,
                ),
            )
            stored_quality = connection.execute(
                """
                SELECT changed_files, insertions, deletions, changed_lines
                FROM experiment_quality
                WHERE run_id = ? AND candidate_id = ?
                """,
                (claim.run_id, candidate_id),
            ).fetchone()
            if stored_quality is not None and quality is None:
                raise ValueError("experiment quality vector is immutable")
            if quality is not None:
                quality_values = (
                    quality.changed_files,
                    quality.insertions,
                    quality.deletions,
                    quality.changed_lines,
                )
                if stored_quality is None:
                    connection.execute(
                        """
                        INSERT INTO experiment_quality(
                            run_id, candidate_id, changed_files, insertions,
                            deletions, changed_lines
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            claim.run_id,
                            candidate_id,
                            *quality_values,
                        ),
                    )
                elif tuple(stored_quality) != quality_values:
                    raise ValueError("experiment quality vector is immutable")
            connection.execute(
                "INSERT INTO events(run_id, kind, payload_json, created_at) VALUES(?, ?, ?, ?)",
                (
                    claim.run_id,
                    "experiment_candidate_recorded",
                    json.dumps(
                        {
                            "candidate_id": candidate_id,
                            "status": status,
                            "score": score,
                            "eligible": eligible,
                        },
                        sort_keys=True,
                    ),
                    now,
                ),
            )

    def record_experiment_ranking(
        self,
        claim: Claim,
        candidate_ids: list[str],
        winner_candidate_id: str | None,
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
                  AND status = 'evaluating'
                """,
                (claim.run_id, claim.generation, now),
            ).fetchone()
            if current is None:
                raise StaleLeaseError(
                    f"run {claim.run_id} generation {claim.generation} is not current"
                )
            stored = {
                row["candidate_id"]: row
                for row in connection.execute(
                    """
                    SELECT candidate.candidate_id, candidate.candidate_commit,
                           candidate.eligible, candidate.score,
                           quality.changed_files, quality.insertions,
                           quality.deletions, quality.changed_lines
                    FROM experiment_candidates AS candidate
                    LEFT JOIN experiment_quality AS quality
                      ON quality.run_id = candidate.run_id
                     AND quality.candidate_id = candidate.candidate_id
                    WHERE candidate.run_id = ?
                    """,
                    (claim.run_id,),
                )
            }
            if (
                len(candidate_ids) != len(set(candidate_ids))
                or set(stored) != set(candidate_ids)
            ):
                raise ValueError("experiment ranking does not match stored candidates")
            expected_ranking = sorted(
                stored,
                key=lambda candidate_id: (
                    not stored[candidate_id]["eligible"],
                    stored[candidate_id]["changed_lines"] is None,
                    stored[candidate_id]["changed_lines"] or 0,
                    stored[candidate_id]["changed_files"] is None,
                    stored[candidate_id]["changed_files"] or 0,
                    candidate_id,
                ),
            )
            expected_winner = next(
                (
                    candidate_id
                    for candidate_id in expected_ranking
                    if stored[candidate_id]["eligible"]
                ),
                None,
            )
            if (
                candidate_ids != expected_ranking
                or winner_candidate_id != expected_winner
            ):
                raise ValueError("experiment ranking is not deterministic")
            connection.execute(
                """
                UPDATE experiment_candidates
                SET selected = 0, updated_at = ?
                WHERE run_id = ?
                """,
                (now, claim.run_id),
            )
            for rank, candidate_id in enumerate(candidate_ids, start=1):
                connection.execute(
                    """
                    UPDATE experiment_candidates
                    SET rank = ?, selected = ?, updated_at = ?
                    WHERE run_id = ? AND candidate_id = ?
                    """,
                    (
                        rank,
                        int(candidate_id == winner_candidate_id),
                        now,
                        claim.run_id,
                        candidate_id,
                    ),
                )
            winner = stored.get(winner_candidate_id) if winner_candidate_id else None
            decision = (
                "selected-for-promotion"
                if winner_candidate_id is not None
                else "no-eligible-candidate"
            )
            connection.execute(
                """
                INSERT INTO promotion_decisions(
                    run_id, candidate_id, candidate_commit, decision,
                    promoted_commit, updated_at
                ) VALUES (?, ?, ?, ?, NULL, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    candidate_id = excluded.candidate_id,
                    candidate_commit = excluded.candidate_commit,
                    decision = excluded.decision,
                    promoted_commit = NULL,
                    updated_at = excluded.updated_at
                """,
                (
                    claim.run_id,
                    winner_candidate_id,
                    winner["candidate_commit"] if winner else None,
                    decision,
                    now,
                ),
            )
            connection.execute(
                "INSERT INTO events(run_id, kind, payload_json, created_at) VALUES(?, ?, ?, ?)",
                (
                    claim.run_id,
                    "experiment_ranked",
                    json.dumps(
                        {
                            "ranking": candidate_ids,
                            "winner_candidate_id": winner_candidate_id,
                            "decision": decision,
                        },
                        sort_keys=True,
                    ),
                    now,
                ),
            )

    def update_promotion_decision(
        self,
        claim: Claim,
        decision: str,
        *,
        controller_lease: ControllerLease,
        promoted_commit: str | None = None,
    ) -> None:
        if decision not in {"awaiting-promotion", "promoted"}:
            raise ValueError("promotion decision is invalid")
        if (decision == "promoted") != (promoted_commit is not None):
            raise ValueError("promotion decision does not match the promoted commit")
        now = _timestamp()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_controller_lease(connection, controller_lease, now)
            current = connection.execute(
                """
                SELECT 1 FROM runs
                WHERE id = ? AND generation = ?
                  AND status IN ('awaiting-promotion', 'succeeded')
                """,
                (claim.run_id, claim.generation),
            ).fetchone()
            if current is None:
                raise StaleLeaseError(
                    f"run {claim.run_id} generation {claim.generation} is not current"
                )
            selected = connection.execute(
                """
                SELECT decision.candidate_commit, candidate.selected,
                       quality.changed_lines
                FROM promotion_decisions AS decision
                JOIN experiment_candidates AS candidate
                  ON candidate.run_id = decision.run_id
                 AND candidate.candidate_id = decision.candidate_id
                JOIN experiment_quality AS quality
                  ON quality.run_id = candidate.run_id
                 AND quality.candidate_id = candidate.candidate_id
                WHERE decision.run_id = ?
                """,
                (claim.run_id,),
            ).fetchone()
            if selected is None or not selected["selected"]:
                raise ValueError("promotion decision has no selected quality vector")
            if promoted_commit is not None and promoted_commit != selected["candidate_commit"]:
                raise ValueError("promoted commit does not match the selected candidate")
            cursor = connection.execute(
                """
                UPDATE promotion_decisions
                SET decision = ?, promoted_commit = ?, updated_at = ?
                WHERE run_id = ?
                """,
                (decision, promoted_commit, now, claim.run_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("promotion decision is not initialized")
            connection.execute(
                "INSERT INTO events(run_id, kind, payload_json, created_at) VALUES(?, ?, ?, ?)",
                (
                    claim.run_id,
                    "promotion_decision",
                    json.dumps(
                        {
                            "decision": decision,
                            "promoted_commit": promoted_commit,
                        },
                        sort_keys=True,
                    ),
                    now,
                ),
            )

    def status(self) -> dict[str, object]:
        if not self.path.is_file():
            return {
                "controller_lease": None,
                "work_items": [],
                "recent_runs": [],
                "candidate_rankings": [],
                "promotion_decisions": [],
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
            candidate_query = """
                SELECT candidate.run_id, candidate.candidate_id,
                       candidate.ordinal, candidate.worktree,
                       candidate.base_commit, candidate.candidate_commit,
                       candidate.status, candidate.classification,
                       candidate.gate_results_json, candidate.score,
                       candidate.all_pass, candidate.non_regressing,
                       candidate.eligible, candidate.rank,
                       candidate.selected, quality.changed_files,
                       quality.insertions, quality.deletions,
                       quality.changed_lines, candidate.updated_at
                FROM experiment_candidates AS candidate
                LEFT JOIN experiment_quality AS quality
                  ON quality.run_id = candidate.run_id
                 AND quality.candidate_id = candidate.candidate_id
                ORDER BY candidate.updated_at DESC, candidate.run_id,
                         candidate.rank, candidate.ordinal
                LIMIT 100
            """
            try:
                candidate_rows = connection.execute(candidate_query)
            except sqlite3.OperationalError as error:
                if "no such table: experiment_candidates" in str(error):
                    candidate_rows = []
                elif "no such table: experiment_quality" not in str(error):
                    raise
                else:
                    candidate_rows = connection.execute(
                        """
                        SELECT run_id, candidate_id, ordinal, worktree,
                               base_commit, candidate_commit, status,
                               classification, gate_results_json, score,
                               all_pass, non_regressing, eligible, rank,
                               selected, NULL AS changed_files,
                               NULL AS insertions, NULL AS deletions,
                               NULL AS changed_lines, updated_at
                        FROM experiment_candidates
                        ORDER BY updated_at DESC, run_id, rank, ordinal
                        LIMIT 100
                        """
                    )
            candidates = [
                {
                    **dict(row),
                    "gate_results": json.loads(row["gate_results_json"]),
                    "all_pass": bool(row["all_pass"]),
                    "non_regressing": bool(row["non_regressing"]),
                    "eligible": bool(row["eligible"]),
                    "selected": bool(row["selected"]),
                }
                for row in candidate_rows
            ]
            for candidate in candidates:
                del candidate["gate_results_json"]
            try:
                promotion_decisions = [
                    dict(row)
                    for row in connection.execute(
                        """
                        SELECT run_id, candidate_id, candidate_commit, decision,
                               promoted_commit, updated_at
                        FROM promotion_decisions
                        ORDER BY updated_at DESC
                        LIMIT 20
                        """
                    )
                ]
            except sqlite3.OperationalError as error:
                if "no such table" not in str(error):
                    raise
                promotion_decisions = []
            return {
                "controller_lease": controller_status,
                "work_items": items,
                "recent_runs": runs,
                "candidate_rankings": candidates,
                "promotion_decisions": promotion_decisions,
            }
