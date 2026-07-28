"""Observation, comparison, action, and re-observation control loop."""

from __future__ import annotations

import hashlib
from contextlib import suppress
from pathlib import Path

from .agent import run_agent
from .config import Config, load_config
from .gitops import (
    GitError,
    cleanup_succeeded_worktree,
    commit_candidate,
    create_worktree,
    current_commit,
    has_changes,
    is_clean,
    promote_fast_forward,
)
from .models import AuthorityLossCause, RunOutcome, RunStatus, WorkKind
from .process import gate_environment, redact_text, run_gate, safe_environment
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

        def source_authority_loss() -> AuthorityLossCause | None:
            try:
                observed_spec_digest = hashlib.sha256(
                    (self.root / "SPEC.json").read_bytes()
                ).hexdigest()
            except OSError:
                observed_spec_digest = None
            observed_base_commit = current_commit(self.root)
            if observed_spec_digest != claim.spec_digest:
                return AuthorityLossCause.SPEC_DIGEST_CHANGED
            if observed_base_commit != claim.base_commit:
                return AuthorityLossCause.BASE_COMMIT_CHANGED
            return None

        authority_loss = source_authority_loss()
        if authority_loss is not None:
            self.store.expire_claim(claim, authority_loss)
            detail = f"authority lost: {authority_loss.value}"
            return RunOutcome(claim.run_id, "stale", detail)

        worktree = None
        execution_state = RunStatus.LEASED
        try:
            heartbeat_interval = max(
                0.1,
                min(30.0, self.config.lease_seconds / 3),
            )

            def revalidate_authority() -> None:
                authority_loss = source_authority_loss()
                if authority_loss is not None:
                    raise StaleLeaseError(
                        f"run {claim.run_id} lost source authority",
                        authority_loss,
                    )
                self.store.renew_lease(claim, self.config.lease_seconds)

            baseline_results: dict[str, bool] = {}
            if claim.work_item.kind is WorkKind.SELF_IMPROVEMENT:
                baseline_environment = gate_environment(
                    safe_environment(
                        self.config.policy.allowed_environment,
                        self.config.policy.redacted_name_fragments,
                    ),
                    self.root,
                )
                for gate in self.config.gates:
                    baseline = run_gate(
                        gate,
                        self.root,
                        baseline_environment,
                        heartbeat=revalidate_authority,
                        heartbeat_interval_seconds=heartbeat_interval,
                    )
                    revalidate_authority()
                    baseline_results[gate.name] = baseline.passed
                    self.store.record_event(
                        claim,
                        "baseline_gate_finished",
                        {
                            "name": baseline.name,
                            "returncode": baseline.returncode,
                            "duration_seconds": round(
                                baseline.duration_seconds,
                                3,
                            ),
                            "timed_out": baseline.timed_out,
                            "stdout": redact_text(
                                baseline.stdout,
                                self.config.policy.redacted_name_fragments,
                            ),
                            "stderr": redact_text(
                                baseline.stderr,
                                self.config.policy.redacted_name_fragments,
                            ),
                        },
                    )
                if not is_clean(self.root):
                    self.store.transition(
                        claim,
                        RunStatus.LEASED,
                        RunStatus.FAILED,
                        detail="baseline gates changed the base repository",
                    )
                    return RunOutcome(
                        claim.run_id,
                        "failed",
                        "baseline gates changed the base repository",
                    )

            worktree = create_worktree(
                self.root,
                self.config.worktree_root,
                claim.run_id,
                claim.work_item.id,
                claim.base_commit,
            )
            authority_loss = source_authority_loss()
            if authority_loss is not None:
                self.store.expire_claim(claim, authority_loss)
                detail = f"authority lost: {authority_loss.value}"
                return RunOutcome(
                    claim.run_id,
                    "stale",
                    detail,
                    worktree.path,
                )
            if not is_clean(self.root):
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

            result = run_agent(
                self.config.agent,
                claim.work_item,
                claim.base_commit,
                worktree.path,
                self.config.result_root / f"{claim.run_id}.txt",
                environment,
                heartbeat=revalidate_authority,
                heartbeat_interval_seconds=heartbeat_interval,
            )
            revalidate_authority()
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

            revalidate_authority()
            candidate = commit_candidate(
                worktree, f"autobuild: complete {claim.work_item.id}"
            )
            revalidate_authority()
            self.store.transition(claim, RunStatus.EXECUTING, RunStatus.EVALUATING)
            execution_state = RunStatus.EVALUATING
            evaluation_environment = gate_environment(environment, worktree.path)
            candidate_results: dict[str, bool] = {}
            for gate in self.config.gates:
                gate_result = run_gate(
                    gate,
                    worktree.path,
                    evaluation_environment,
                    heartbeat=revalidate_authority,
                    heartbeat_interval_seconds=heartbeat_interval,
                )
                revalidate_authority()
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
                candidate_results[gate.name] = gate_result.passed
                if not gate_result.passed:
                    if claim.work_item.kind is WorkKind.SELF_IMPROVEMENT:
                        gate_pass_deltas = {
                            name: int(passed) - int(baseline_results[name])
                            for name, passed in candidate_results.items()
                        }
                        self.store.record_event(
                            claim,
                            "self_improvement_evaluated",
                            {
                                "classification": (
                                    "regression"
                                    if any(delta < 0 for delta in gate_pass_deltas.values())
                                    else "no-improvement"
                                ),
                                "failed_gate": gate.name,
                                "baseline_gates": baseline_results,
                                "candidate_gates": candidate_results,
                                "gate_pass_deltas": gate_pass_deltas,
                            },
                        )
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
            if claim.work_item.kind is WorkKind.SELF_IMPROVEMENT:
                gate_pass_deltas = {
                    name: int(candidate_results[name]) - int(passed)
                    for name, passed in baseline_results.items()
                }
                passing_gate_count_delta = sum(candidate_results.values()) - sum(
                    baseline_results.values()
                )
                self.store.record_event(
                    claim,
                    "self_improvement_evaluated",
                    {
                        "classification": (
                            "improvement"
                            if passing_gate_count_delta > 0
                            else "non-regression"
                        ),
                        "baseline_gates": baseline_results,
                        "candidate_gates": candidate_results,
                        "gate_pass_deltas": gate_pass_deltas,
                        "passing_gate_count_delta": passing_gate_count_delta,
                    },
                )
            authority_loss = source_authority_loss()
            if authority_loss is not None:
                self.store.expire_claim(claim, authority_loss)
                detail = f"authority lost: {authority_loss.value}"
                return RunOutcome(
                    claim.run_id,
                    "stale",
                    detail,
                    worktree.path,
                )
            if not is_clean(self.root):
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
            revalidate_authority()
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
            detail = f"promoted {promoted}"
            if self.config.cleanup_succeeded_worktrees:
                try:
                    cleanup_succeeded_worktree(
                        self.root,
                        self.config.worktree_root,
                        worktree,
                        promoted,
                    )
                    self.store.record_terminal_event(
                        claim,
                        "worktree_cleaned",
                        {"path": str(worktree.path), "branch": worktree.branch},
                    )
                    detail += "; successful worktree cleaned"
                except GitError as cleanup_error:
                    self.store.record_terminal_event(
                        claim,
                        "worktree_cleanup_failed",
                        {"detail": str(cleanup_error)},
                    )
                    detail += f"; cleanup preserved: {cleanup_error}"
            return RunOutcome(
                claim.run_id,
                "succeeded",
                detail,
                worktree.path,
            )
        except StaleLeaseError as error:
            self.store.expire_claim(claim, error.cause)
            detail = f"authority lost: {error.cause.value}"
            return RunOutcome(
                claim.run_id,
                "stale",
                detail,
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
        except Exception as error:
            detail = redact_text(
                f"controller error: {type(error).__name__}: {error}",
                self.config.policy.redacted_name_fragments,
            )
            with suppress(Exception):
                self.store.transition(
                    claim,
                    execution_state,
                    RunStatus.FAILED,
                    detail=detail,
                )
            return RunOutcome(
                claim.run_id,
                "failed",
                detail,
                worktree.path if worktree else None,
            )
