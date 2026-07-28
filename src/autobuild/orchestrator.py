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
    is_clean,
    promote_fast_forward,
)
from .models import RunOutcome, RunStatus, WorkKind
from .process import run_gate, safe_environment
from .spec import load_spec
from .state import StateStore


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
        try:
            worktree = create_worktree(
                self.root,
                self.config.worktree_root,
                claim.run_id,
                claim.work_item.id,
            )
            self.store.transition(
                claim,
                RunStatus.LEASED,
                RunStatus.EXECUTING,
                worktree=worktree.path,
            )
            environment = safe_environment(self.config.policy.allowed_environment)
            result = run_agent(
                self.config.agent,
                claim.work_item,
                claim.base_commit,
                worktree.path,
                self.config.result_root / f"{claim.run_id}.txt",
                environment,
            )
            self.store.record_event(
                claim,
                "agent_finished",
                {
                    "returncode": result.returncode,
                    "timed_out": result.timed_out,
                    "summary": result.summary,
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

            self.store.transition(claim, RunStatus.EXECUTING, RunStatus.EVALUATING)
            for gate in self.config.gates:
                gate_result = run_gate(gate, worktree.path, environment)
                self.store.record_event(
                    claim,
                    "gate_finished",
                    {
                        "name": gate_result.name,
                        "returncode": gate_result.returncode,
                        "duration_seconds": round(gate_result.duration_seconds, 3),
                        "timed_out": gate_result.timed_out,
                        "stdout": gate_result.stdout,
                        "stderr": gate_result.stderr,
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

            current_spec = load_spec(self.root / "SPEC.json")
            if (
                current_spec.digest != claim.spec_digest
                or current_commit(self.root) != claim.base_commit
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
            candidate = commit_candidate(
                worktree, f"autobuild: complete {claim.work_item.id}"
            )
            if not self.config.auto_promote:
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
        except GitError as error:
            expected = RunStatus.LEASED if worktree is None else RunStatus.EXECUTING
            with suppress(Exception):
                self.store.transition(
                    claim, expected, RunStatus.FAILED, detail=f"git error: {error}"
                )
            return RunOutcome(
                claim.run_id,
                "failed",
                f"git error: {error}",
                worktree.path if worktree else None,
            )
