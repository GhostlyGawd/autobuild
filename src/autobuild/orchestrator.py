"""Observation, comparison, action, and re-observation control loop."""

from __future__ import annotations

import hashlib
import time
import uuid
from contextlib import suppress
from dataclasses import dataclass, field, replace
from pathlib import Path

from .agent import run_agent
from .config import Config, load_config
from .gitops import (
    CandidateArtifactError,
    GitError,
    Worktree,
    cleanup_succeeded_worktree,
    commit_candidate,
    create_worktree,
    current_commit,
    has_changes,
    is_clean,
    measure_change_surface,
    promote_fast_forward,
)
from .models import (
    AuthorityLossCause,
    ChangeSurface,
    ControllerLease,
    RunOutcome,
    RunStatus,
    WorkKind,
)
from .process import gate_environment, redact_text, run_gate, safe_environment
from .spec import load_spec
from .state import ControllerLeaseError, StaleLeaseError, StateStore


@dataclass
class _CandidateExperiment:
    candidate_id: str
    ordinal: int
    worktree: Worktree
    remaining_seconds: float
    candidate_commit: str | None = None
    agent_passed: bool = False
    gate_results: dict[str, bool | None] = field(default_factory=dict)
    score: int = 0
    all_pass: bool = False
    non_regressing: bool = False
    eligible: bool = False
    classification: str = "pending"
    quality: ChangeSurface | None = None


class Orchestrator:
    def __init__(self, root: Path, config: Config | None = None) -> None:
        self.root = root.resolve()
        self.config = config or load_config(self.root)
        self.store = StateStore(self.config.state_path)

    def reconcile_once(self, *, kind: WorkKind | None = None) -> RunOutcome:
        try:
            self.store.initialize()
            controller_lease = self.store.acquire_controller_lease(
                self.root,
                self.config.lease_seconds,
                owner_id=str(uuid.uuid4()),
            )
        except ControllerLeaseError as error:
            return RunOutcome(None, "deferred", str(error))
        try:
            return self._reconcile_owned(controller_lease, kind=kind)
        finally:
            with suppress(Exception):
                self.store.release_controller_lease(controller_lease)

    def _reconcile_owned(
        self,
        controller_lease: ControllerLease,
        *,
        kind: WorkKind | None = None,
    ) -> RunOutcome:
        specification = load_spec(self.root / "SPEC.json")
        self.store.sync_spec(
            specification,
            controller_lease=controller_lease,
        )
        if not is_clean(self.root):
            return RunOutcome(None, "deferred", "base repository has uncommitted changes")
        base_commit = current_commit(self.root)
        recovered = self.store.recover_promotion(
            specification,
            base_commit,
            controller_lease=controller_lease,
        )
        if recovered is not None:
            return recovered
        claim = self.store.claim_next(
            specification,
            base_commit,
            self.config.lease_seconds,
            self.config.max_attempts,
            controller_lease=controller_lease,
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
            self.store.expire_claim(
                claim,
                authority_loss,
                controller_lease=controller_lease,
            )
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
                self.store.renew_controller_lease(
                    controller_lease,
                    self.config.lease_seconds,
                )
                self.store.renew_lease(
                    claim,
                    self.config.lease_seconds,
                    controller_lease=controller_lease,
                )

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
                        controller_lease=controller_lease,
                    )
                if not is_clean(self.root):
                    self.store.transition(
                        claim,
                        RunStatus.LEASED,
                        RunStatus.FAILED,
                        controller_lease=controller_lease,
                        detail="baseline gates changed the base repository",
                    )
                    return RunOutcome(
                        claim.run_id,
                        "failed",
                        "baseline gates changed the base repository",
                    )

            environment = safe_environment(
                self.config.policy.allowed_environment,
                self.config.policy.redacted_name_fragments,
            )
            is_self_improvement = (
                claim.work_item.kind is WorkKind.SELF_IMPROVEMENT
            )
            experiment_count = (
                self.config.self_improvement.max_candidates
                if is_self_improvement
                else 1
            )
            candidates: list[_CandidateExperiment] = []
            for ordinal in range(1, experiment_count + 1):
                if candidates:
                    revalidate_authority()
                candidate_id = f"candidate-{ordinal:03d}"
                worktree_id = (
                    f"{ordinal:03d}-{claim.run_id}"
                    if is_self_improvement
                    else claim.run_id
                )
                worktree = create_worktree(
                    self.root,
                    self.config.worktree_root,
                    worktree_id,
                    claim.work_item.id,
                    claim.base_commit,
                )
                authority_loss = source_authority_loss()
                if authority_loss is not None:
                    self.store.expire_claim(
                        claim,
                        authority_loss,
                        controller_lease=controller_lease,
                    )
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
                        RunStatus.LEASED
                        if not candidates
                        else RunStatus.EXECUTING,
                        RunStatus.STALE,
                        controller_lease=controller_lease,
                        detail="desired state changed at dispatch",
                        worktree=worktree.path,
                    )
                    return RunOutcome(
                        claim.run_id,
                        "stale",
                        "desired state changed at dispatch",
                        worktree.path,
                    )
                if not candidates:
                    self.store.transition(
                        claim,
                        RunStatus.LEASED,
                        RunStatus.EXECUTING,
                        controller_lease=controller_lease,
                        worktree=worktree.path,
                    )
                    execution_state = RunStatus.EXECUTING
                experiment = _CandidateExperiment(
                    candidate_id=candidate_id,
                    ordinal=ordinal,
                    worktree=worktree,
                    remaining_seconds=float(
                        self.config.self_improvement.candidate_timeout_seconds
                        if is_self_improvement
                        else self.config.agent.timeout_seconds
                    ),
                )
                candidates.append(experiment)
                if is_self_improvement:
                    self.store.record_experiment_candidate(
                        claim,
                        candidate_id=candidate_id,
                        ordinal=ordinal,
                        worktree=worktree.path,
                        candidate_commit=None,
                        status="executing",
                        classification="pending",
                        gate_results={},
                        score=0,
                        all_pass=False,
                        non_regressing=False,
                        eligible=False,
                        quality=None,
                        controller_lease=controller_lease,
                    )
                agent_timeout = min(
                    float(self.config.agent.timeout_seconds),
                    experiment.remaining_seconds,
                )
                agent_config = replace(
                    self.config.agent,
                    timeout_seconds=agent_timeout,
                )
                agent_started = time.monotonic()
                result = run_agent(
                    agent_config,
                    claim.work_item,
                    claim.base_commit,
                    worktree.path,
                    self.config.result_root
                    / (
                        f"{claim.run_id}-{candidate_id}.txt"
                        if is_self_improvement
                        else f"{claim.run_id}.txt"
                    ),
                    environment,
                    heartbeat=revalidate_authority,
                    heartbeat_interval_seconds=heartbeat_interval,
                )
                experiment.remaining_seconds = max(
                    0.0,
                    experiment.remaining_seconds
                    - (time.monotonic() - agent_started),
                )
                revalidate_authority()
                event_payload = {
                    "returncode": result.returncode,
                    "timed_out": result.timed_out,
                    "summary": redact_text(
                        result.summary,
                        self.config.policy.redacted_name_fragments,
                    ),
                }
                if is_self_improvement:
                    event_payload["candidate_id"] = candidate_id
                self.store.record_event(
                    claim,
                    "agent_finished",
                    event_payload,
                    controller_lease=controller_lease,
                )
                if not result.passed:
                    experiment.classification = (
                        "timed-out" if result.timed_out else "agent-failed"
                    )
                    if is_self_improvement:
                        experiment.gate_results = {
                            gate.name: None for gate in self.config.gates
                        }
                        self.store.record_experiment_candidate(
                            claim,
                            candidate_id=candidate_id,
                            ordinal=ordinal,
                            worktree=worktree.path,
                            candidate_commit=None,
                            status="failed",
                            classification=experiment.classification,
                            gate_results=experiment.gate_results,
                            score=0,
                            all_pass=False,
                            non_regressing=False,
                            eligible=False,
                            quality=None,
                            controller_lease=controller_lease,
                        )
                        continue
                    self.store.transition(
                        claim,
                        RunStatus.EXECUTING,
                        RunStatus.FAILED,
                        controller_lease=controller_lease,
                        detail="agent process failed or timed out",
                    )
                    return RunOutcome(
                        claim.run_id,
                        "failed",
                        "agent process failed or timed out",
                        worktree.path,
                    )

                revalidate_authority()
                try:
                    experiment.candidate_commit = commit_candidate(
                        worktree,
                        f"autobuild: complete {claim.work_item.id} ({candidate_id})"
                        if is_self_improvement
                        else f"autobuild: complete {claim.work_item.id}",
                    )
                except CandidateArtifactError:
                    if not is_self_improvement:
                        raise
                    revalidate_authority()
                    experiment.classification = "artifact-rejected"
                    experiment.gate_results = {
                        gate.name: None for gate in self.config.gates
                    }
                    self.store.record_experiment_candidate(
                        claim,
                        candidate_id=candidate_id,
                        ordinal=ordinal,
                        worktree=worktree.path,
                        candidate_commit=None,
                        status="rejected",
                        classification=experiment.classification,
                        gate_results=experiment.gate_results,
                        score=0,
                        all_pass=False,
                        non_regressing=False,
                        eligible=False,
                        quality=None,
                        controller_lease=controller_lease,
                    )
                    self.store.record_event(
                        claim,
                        "candidate_artifact_rejected",
                        {
                            "candidate_id": candidate_id,
                            "classification": experiment.classification,
                        },
                        controller_lease=controller_lease,
                    )
                    continue
                experiment.agent_passed = True
                revalidate_authority()

            self.store.transition(
                claim,
                RunStatus.EXECUTING,
                RunStatus.EVALUATING,
                controller_lease=controller_lease,
            )
            execution_state = RunStatus.EVALUATING
            for experiment in candidates:
                if not experiment.agent_passed:
                    continue
                worktree = experiment.worktree
                evaluation_environment = gate_environment(
                    environment,
                    worktree.path,
                )
                for gate in self.config.gates:
                    if (
                        is_self_improvement
                        and experiment.remaining_seconds <= 0
                    ):
                        gate_result = None
                        experiment.gate_results[gate.name] = False
                        gate_payload: dict[str, object] = {
                            "name": gate.name,
                            "returncode": None,
                            "duration_seconds": 0.0,
                            "timed_out": True,
                            "stdout": "",
                            "stderr": "candidate experiment duration exhausted",
                        }
                    else:
                        bounded_gate = (
                            replace(
                                gate,
                                timeout_seconds=min(
                                    float(gate.timeout_seconds),
                                    experiment.remaining_seconds,
                                ),
                            )
                            if is_self_improvement
                            else gate
                        )
                        gate_started = time.monotonic()
                        gate_result = run_gate(
                            bounded_gate,
                            worktree.path,
                            evaluation_environment,
                            heartbeat=revalidate_authority,
                            heartbeat_interval_seconds=heartbeat_interval,
                        )
                        if is_self_improvement:
                            experiment.remaining_seconds = max(
                                0.0,
                                experiment.remaining_seconds
                                - (time.monotonic() - gate_started),
                            )
                        revalidate_authority()
                        experiment.gate_results[gate.name] = gate_result.passed
                        gate_payload = {
                            "name": gate_result.name,
                            "returncode": gate_result.returncode,
                            "duration_seconds": round(
                                gate_result.duration_seconds,
                                3,
                            ),
                            "timed_out": gate_result.timed_out,
                            "stdout": redact_text(
                                gate_result.stdout,
                                self.config.policy.redacted_name_fragments,
                            ),
                            "stderr": redact_text(
                                gate_result.stderr,
                                self.config.policy.redacted_name_fragments,
                            ),
                        }
                    if is_self_improvement:
                        gate_payload["candidate_id"] = experiment.candidate_id
                    self.store.record_event(
                        claim,
                        "gate_finished",
                        gate_payload,
                        controller_lease=controller_lease,
                    )
                    if not is_self_improvement and not experiment.gate_results[
                        gate.name
                    ]:
                        self.store.transition(
                            claim,
                            RunStatus.EVALUATING,
                            RunStatus.FAILED,
                            controller_lease=controller_lease,
                            detail=f"gate failed: {gate.name}",
                        )
                        return RunOutcome(
                            claim.run_id,
                            "failed",
                            f"gate failed: {gate.name}",
                            worktree.path,
                        )

                unchanged = (
                    not has_changes(worktree)
                    and current_commit(worktree.path)
                    == experiment.candidate_commit
                )
                if not is_self_improvement and not unchanged:
                    self.store.transition(
                        claim,
                        RunStatus.EVALUATING,
                        RunStatus.FAILED,
                        controller_lease=controller_lease,
                        detail="verification gates changed the candidate",
                    )
                    return RunOutcome(
                        claim.run_id,
                        "failed",
                        "verification gates changed the candidate",
                        worktree.path,
                    )
                if not is_self_improvement:
                    continue
                gate_pass_deltas = {
                    name: int(experiment.gate_results[name]) - int(passed)
                    for name, passed in baseline_results.items()
                }
                experiment.score = sum(experiment.gate_results.values())
                experiment.all_pass = all(experiment.gate_results.values())
                experiment.non_regressing = not any(
                    delta < 0 for delta in gate_pass_deltas.values()
                )
                experiment.eligible = (
                    unchanged
                    and experiment.all_pass
                    and experiment.non_regressing
                )
                experiment.quality = measure_change_surface(
                    worktree.path,
                    claim.base_commit,
                    experiment.candidate_commit,
                )
                passing_gate_count_delta = experiment.score - sum(
                    baseline_results.values()
                )
                if not unchanged:
                    experiment.classification = "mutated"
                elif any(delta < 0 for delta in gate_pass_deltas.values()):
                    experiment.classification = "regression"
                elif experiment.all_pass and passing_gate_count_delta > 0:
                    experiment.classification = "improvement"
                elif experiment.all_pass:
                    experiment.classification = "non-regression"
                else:
                    experiment.classification = "no-improvement"
                self.store.record_experiment_candidate(
                    claim,
                    candidate_id=experiment.candidate_id,
                    ordinal=experiment.ordinal,
                    worktree=worktree.path,
                    candidate_commit=experiment.candidate_commit,
                    status="evaluated",
                    classification=experiment.classification,
                    gate_results=experiment.gate_results,
                    score=experiment.score,
                    all_pass=experiment.all_pass,
                    non_regressing=experiment.non_regressing,
                    eligible=experiment.eligible,
                    quality=experiment.quality,
                    controller_lease=controller_lease,
                )
                self.store.record_event(
                    claim,
                    "self_improvement_evaluated",
                    {
                        "candidate_id": experiment.candidate_id,
                        "classification": experiment.classification,
                        "baseline_gates": baseline_results,
                        "candidate_gates": experiment.gate_results,
                        "gate_pass_deltas": gate_pass_deltas,
                        "passing_gate_count_delta": passing_gate_count_delta,
                        "score": experiment.score,
                        "eligible": experiment.eligible,
                        "quality": {
                            "changed_files": experiment.quality.changed_files,
                            "insertions": experiment.quality.insertions,
                            "deletions": experiment.quality.deletions,
                            "changed_lines": experiment.quality.changed_lines,
                        },
                    },
                    controller_lease=controller_lease,
                )

            if is_self_improvement:
                ranked_candidates = sorted(
                    candidates,
                    key=lambda experiment: (
                        not experiment.eligible,
                        experiment.quality is None,
                        experiment.quality.changed_lines
                        if experiment.quality is not None
                        else 0,
                        experiment.quality is None,
                        experiment.quality.changed_files
                        if experiment.quality is not None
                        else 0,
                        experiment.candidate_id,
                    ),
                )
                winner = next(
                    (
                        experiment
                        for experiment in ranked_candidates
                        if experiment.eligible
                    ),
                    None,
                )
                self.store.record_experiment_ranking(
                    claim,
                    [
                        experiment.candidate_id
                        for experiment in ranked_candidates
                    ],
                    winner.candidate_id if winner else None,
                    controller_lease=controller_lease,
                )
                if winner is None:
                    self.store.transition(
                        claim,
                        RunStatus.EVALUATING,
                        RunStatus.FAILED,
                        controller_lease=controller_lease,
                        detail="no eligible self-improvement candidate",
                    )
                    return RunOutcome(
                        claim.run_id,
                        "failed",
                        "no eligible self-improvement candidate",
                        candidates[0].worktree.path,
                    )
                worktree = winner.worktree
                candidate = winner.candidate_commit
            else:
                winner = None
                worktree = candidates[0].worktree
                candidate = candidates[0].candidate_commit
            if candidate is None:
                raise GitError("candidate commit is missing after evaluation")
            authority_loss = source_authority_loss()
            if authority_loss is not None:
                self.store.expire_claim(
                    claim,
                    authority_loss,
                    controller_lease=controller_lease,
                )
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
                    controller_lease=controller_lease,
                    detail="desired state changed before promotion",
                )
                return RunOutcome(
                    claim.run_id,
                    "stale",
                    "desired state changed before promotion",
                    worktree.path,
                )
            self.store.transition(
                claim,
                RunStatus.EVALUATING,
                RunStatus.PROMOTING,
                controller_lease=controller_lease,
            )
            execution_state = RunStatus.PROMOTING
            revalidate_authority()
            if not self.config.auto_promote:
                self.store.transition(
                    claim,
                    RunStatus.PROMOTING,
                    RunStatus.AWAITING_PROMOTION,
                    controller_lease=controller_lease,
                    detail=f"verified candidate {candidate}",
                )
                if is_self_improvement:
                    self.store.update_promotion_decision(
                        claim,
                        "awaiting-promotion",
                        controller_lease=controller_lease,
                    )
                return RunOutcome(
                    claim.run_id,
                    "awaiting-promotion",
                    f"verified candidate {candidate}",
                    worktree.path,
                )
            self.store.record_promotion_intent(
                claim,
                candidate,
                worktree.path,
                controller_lease=controller_lease,
            )
            with self.store.controller_operation(
                controller_lease,
                self.config.lease_seconds,
            ):
                promoted = promote_fast_forward(
                    self.root,
                    worktree,
                    claim.base_commit,
                )
            self.store.transition(
                claim,
                RunStatus.PROMOTING,
                RunStatus.SUCCEEDED,
                controller_lease=controller_lease,
                detail=f"promoted {promoted}",
            )
            if is_self_improvement:
                self.store.update_promotion_decision(
                    claim,
                    "promoted",
                    controller_lease=controller_lease,
                    promoted_commit=promoted,
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
                        controller_lease=controller_lease,
                    )
                    detail += "; successful worktree cleaned"
                except GitError as cleanup_error:
                    self.store.record_terminal_event(
                        claim,
                        "worktree_cleanup_failed",
                        {"detail": str(cleanup_error)},
                        controller_lease=controller_lease,
                    )
                    detail += f"; cleanup preserved: {cleanup_error}"
            return RunOutcome(
                claim.run_id,
                "succeeded",
                detail,
                worktree.path,
            )
        except ControllerLeaseError:
            return RunOutcome(
                claim.run_id,
                "deferred",
                "controller ownership was lost; recovery requires lease expiry",
                worktree.path if worktree else None,
            )
        except StaleLeaseError as error:
            with suppress(ControllerLeaseError):
                self.store.expire_claim(
                    claim,
                    error.cause,
                    controller_lease=controller_lease,
                )
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
                    controller_lease=controller_lease,
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
                    controller_lease=controller_lease,
                    detail=detail,
                )
            return RunOutcome(
                claim.run_id,
                "failed",
                detail,
                worktree.path if worktree else None,
            )
