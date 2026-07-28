"""Observation, comparison, action, and re-observation control loop."""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path

from .agent import run_agent
from .config import Config, load_config
from .gitops import (
    GitError,
    commit_candidate,
    create_worktree,
    current_commit,
    has_changes,
    is_clean,
    promote_fast_forward,
)
from .models import RunOutcome, RunStatus, WorkKind
from .process import redact_text, run_gate, safe_environment
from .spec import load_spec
from .state import StaleLeaseError, StateStore


class Orchestrator:
    def __init__(self, root: Path, config: Config | None = None) -> None:
        self.root = root.resolve()
        self.config = config or load_config(self.root)
        self.store = StateStore(self.config.state_path)

    def reconcile_once(self, *, kind: WorkKind | None = None) -> RunOutcome:
        self.store.initialize()
        specification = load_spec(self.root / "SPEC.json")
        self.store.sync_spec(specification)
        if not is_clean(self.root):
            return RunOutcome(None, "deferred", "base repository has uncommitted changes")
        base_commit = current_commit(self.root)
        claim = self.store.claim_next(
            specification,
            base_commit,
            self.config.lease_seconds,
            self.config.max_attempts,
            kind=kind,
        )
        if claim is None:
            return RunOutcome(None, "idle", "no eligible work item")

        current_spec = load_spec(self.root / "SPEC.json")
        if (
            current_spec.digest != claim.spec_digest
            or current_commit(self.root) != claim.base_commit
        ):
            self.store.transition(
                claim,
                RunStatus.LEASED,
                RunStatus.STALE,
                detail="desired state changed before dispatch",
            )
            return RunOutcome(claim.run_id, "stale", "desired state changed before dispatch")

        worktree = None
        execution_state = RunStatus.LEASED
        try:
            worktree = create_worktree(
                self.root,
                self.config.worktree_root,
                claim.run_id,
                claim.work_item.id,
                claim.base_commit,
            )
            current_spec = load_spec(self.root / "SPEC.json")
            if (
                current_spec.digest != claim.spec_digest
                or current_commit(self.root) != claim.base_commit
                or not is_clean(self.root)
            ):
                self.store.transition(
                    claim,
                    RunStatus.LEASED,
                    RunStatus.STALE,
                    detail="desired state changed at dispatch",
                    worktree=worktree.path,
                )
                return RunOutcome(
                    claim.run_id,
                    "stale",
                    "desired state changed at dispatch",
                    worktree.path,
                )
            self.store.transition(
                claim,
                RunStatus.LEASED,
                RunStatus.EXECUTING,
                worktree=worktree.path,
            )
            execution_state = RunStatus.EXECUTING
            environment = safe_environment(
                self.config.policy.allowed_environment,
                self.config.policy.redacted_name_fragments,
            )
            heartbeat_interval = max(
                0.1,
                min(30.0, self.config.lease_seconds / 3),
            )

            def renew_lease() -> None:
                self.store.renew_lease(claim, self.config.lease_seconds)

            result = run_agent(
                self.config.agent,
                claim.work_item,
                claim.base_commit,
                worktree.path,
                self.config.result_root / f"{claim.run_id}.txt",
                environment,
                heartbeat=renew_lease,
                heartbeat_interval_seconds=heartbeat_interval,
            )
            renew_lease()
            self.store.record_event(
                claim,
                "agent_finished",
                {
                    "returncode": result.returncode,
                    "timed_out": result.timed_out,
                    "summary": redact_text(
                        result.summary,
                        self.config.policy.redacted_name_fragments,
                    ),
                },
            )
            if not result.passed:
                self.store.transition(
                    claim,
                    RunStatus.EXECUTING,
                    RunStatus.FAILED,
                    detail="agent process failed or timed out",
                )
                return RunOutcome(
                    claim.run_id,
                    "failed",
                    "agent process failed or timed out",
                    worktree.path,
                )

            renew_lease()
            candidate = commit_candidate(
                worktree, f"autobuild: complete {claim.work_item.id}"
            )
            renew_lease()
            self.store.transition(claim, RunStatus.EXECUTING, RunStatus.EVALUATING)
            execution_state = RunStatus.EVALUATING
            for gate in self.config.gates:
                gate_result = run_gate(
                    gate,
                    worktree.path,
                    environment,
                    heartbeat=renew_lease,
                    heartbeat_interval_seconds=heartbeat_interval,
                )
                renew_lease()
                self.store.record_event(
                    claim,
                    "gate_finished",
                    {
                        "name": gate_result.name,
                        "returncode": gate_result.returncode,
                        "duration_seconds": round(gate_result.duration_seconds, 3),
                        "timed_out": gate_result.timed_out,
                        "stdout": redact_text(
                            gate_result.stdout,
                            self.config.policy.redacted_name_fragments,
                        ),
                        "stderr": redact_text(
                            gate_result.stderr,
                            self.config.policy.redacted_name_fragments,
                        ),
                    },
                )
                if not gate_result.passed:
                    self.store.transition(
                        claim,
                        RunStatus.EVALUATING,
                        RunStatus.FAILED,
                        detail=f"gate failed: {gate.name}",
                    )
                    return RunOutcome(
                        claim.run_id,
                        "failed",
                        f"gate failed: {gate.name}",
                        worktree.path,
                    )

            if has_changes(worktree) or current_commit(worktree.path) != candidate:
                self.store.transition(
                    claim,
                    RunStatus.EVALUATING,
                    RunStatus.FAILED,
                    detail="verification gates changed the candidate",
                )
                return RunOutcome(
                    claim.run_id,
                    "failed",
                    "verification gates changed the candidate",
                    worktree.path,
                )
            current_spec = load_spec(self.root / "SPEC.json")
            if (
                current_spec.digest != claim.spec_digest
                or current_commit(self.root) != claim.base_commit
                or not is_clean(self.root)
            ):
                self.store.transition(
                    claim,
                    RunStatus.EVALUATING,
                    RunStatus.STALE,
                    detail="desired state changed before promotion",
                )
                return RunOutcome(
                    claim.run_id,
                    "stale",
                    "desired state changed before promotion",
                    worktree.path,
                )
            self.store.transition(claim, RunStatus.EVALUATING, RunStatus.PROMOTING)
            execution_state = RunStatus.PROMOTING
            if not self.config.auto_promote:
                self.store.transition(
                    claim,
                    RunStatus.PROMOTING,
                    RunStatus.AWAITING_PROMOTION,
                    detail=f"verified candidate {candidate}",
                )
                return RunOutcome(
                    claim.run_id,
                    "awaiting-promotion",
                    f"verified candidate {candidate}",
                    worktree.path,
                )
            promoted = promote_fast_forward(self.root, worktree, claim.base_commit)
            self.store.transition(
                claim,
                RunStatus.PROMOTING,
                RunStatus.SUCCEEDED,
                detail=f"promoted {promoted}",
            )
            return RunOutcome(
                claim.run_id,
                "succeeded",
                f"promoted {promoted}",
                worktree.path,
            )
        except StaleLeaseError as error:
            self.store.expire_claim(claim, f"lease lost: {error}")
            return RunOutcome(
                claim.run_id,
                "stale",
                f"lease lost: {error}",
                worktree.path if worktree else None,
            )
        except GitError as error:
            with suppress(Exception):
                self.store.transition(
                    claim,
                    execution_state,
                    RunStatus.FAILED,
                    detail=f"git error: {error}",
                )
            return RunOutcome(
                claim.run_id,
                "failed",
                f"git error: {error}",
                worktree.path if worktree else None,
            )
