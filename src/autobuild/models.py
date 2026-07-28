"""Typed contracts shared by the control loop."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class WorkKind(StrEnum):
    PRODUCT = "product"
    SELF_IMPROVEMENT = "self-improvement"


class WorkStatus(StrEnum):
    READY = "ready"
    ACTIVE = "active"
    ACHIEVED = "achieved"
    BLOCKED = "blocked"
    SUPERSEDED = "superseded"


class RunStatus(StrEnum):
    LEASED = "leased"
    EXECUTING = "executing"
    EVALUATING = "evaluating"
    PROMOTING = "promoting"
    AWAITING_PROMOTION = "awaiting-promotion"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    STALE = "stale"

    @property
    def terminal(self) -> bool:
        return self in {
            self.AWAITING_PROMOTION,
            self.SUCCEEDED,
            self.FAILED,
            self.STALE,
        }


@dataclass(frozen=True)
class WorkItem:
    id: str
    kind: WorkKind
    priority: int
    objective: str
    acceptance: tuple[str, ...]
    spec_digest: str


@dataclass(frozen=True)
class Claim:
    run_id: str
    work_item: WorkItem
    generation: int
    base_commit: str
    spec_digest: str
    lease_expires_at: str


@dataclass(frozen=True)
class Gate:
    name: str
    command: tuple[str, ...]
    timeout_seconds: int


@dataclass(frozen=True)
class GateResult:
    name: str
    command: tuple[str, ...]
    returncode: int | None
    duration_seconds: float
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def passed(self) -> bool:
        return not self.timed_out and self.returncode == 0


@dataclass(frozen=True)
class AgentResult:
    returncode: int | None
    summary: str
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def passed(self) -> bool:
        return not self.timed_out and self.returncode == 0


@dataclass(frozen=True)
class RunOutcome:
    run_id: str | None
    status: str
    detail: str
    worktree: Path | None = None
