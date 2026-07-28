# Durable workpad

## Identity and authoritative state

- Repository: `GhostlyGawd/autobuild`
- Default branch: `main`
- Starting commit: `e45111d30dcd29e618e3774c3f2884ba80a83aa3`
- Portfolio status: untracked
- Productization basis: provisional public-product observation from
  `GhostlyGawd/repo-audit` commit
  `907f0759f9d08f478cd5384ad88e50963f1af79a`
- Active outcome: Build and dogfood a safe, resumable, recursively
  self-improving harness for autonomous engineering.
- Desired-state authority: `SPEC.json`
- Execution authority: `.autobuild/state.db`
- Source authority: Git

## Plan

- [x] Establish the authority, lifecycle, security, and documentation contracts.
- [x] Implement SPEC loading, durable state, fenced claims, the Codex adapter,
  gate execution, isolated worktrees, and fast-forward promotion.
- [x] Prove the current lifecycle and security matrix with deterministic tests.
- [ ] Dogfood validation and state inspection in this repository.
- [ ] Run the first bounded self-improvement experiment.
- [ ] Add lease renewal, terminal cleanup reconciliation, and comparative
  improvement metrics.

## Acceptance criteria

- A stale lease generation cannot change current run state.
- Dispatch stops if the SPEC revision or base commit changed.
- Promotion stops if a verification gate fails or the base commit changed.
- Restart recovery preserves nonterminal evidence and rejects stale events.
- Configured commands run without a shell and receive an allowlisted
  environment.
- Self-improvement uses the same safety gates as product work.
- Automated writing checks do not claim full ASD-STE100 compliance.
- Current setup, architecture, security, limitation, and lifecycle documents
  agree with observable behavior.

## Alignment table

| Contract item | Normative level | Implementation | Test | Docs/example | Status |
|---|---|---|---|---|---|
| SPEC owns desired state | Required | `spec.py`, `orchestrator.py` | SPEC and orchestrator tests | README, architecture | Proven for current local flow |
| SQLite owns leases and events | Required | `state.py` | State lifecycle tests | architecture | Proven for current local flow |
| Generation fences stale events | Required | `state.py` | Stale and restart tests | lifecycle contract | Proven |
| Fresh read before dispatch and promotion | Required | `orchestrator.py` | Git and orchestrator tests | architecture | Partly proven; dispatch race injection remains |
| Shell-free gate execution | Required | `process.py` | Shell-injection negative | SECURITY | Proven |
| Secret containment and evidence redaction | Required | `process.py`, `orchestrator.py` | Environment and redaction negatives | SECURITY | Proven for configured and known forms |
| Candidate immutability after verification | Required | `orchestrator.py`, `gitops.py` | Gate-mutation negative | README, architecture | Proven |
| Isolated, fast-forward-only promotion | Required | `gitops.py` | Git integration tests | README, architecture | Proven |
| Bounded self-improvement | Required | normal work-item route | Pending | SPEC, architecture | Partial |
| Full STE claim requires human reviews | Required | repository policy and docs | Text audit pending | README, AGENTS | Implemented; not released as compliant |

## Implementation progress

The first implementation slice provides a standard-library runtime and a
Codex CLI adapter. The controller commits a candidate before evaluation and
rejects gate mutations. It preserves failed, stale, and manual-handoff
worktrees. It does not yet renew an active lease or clean terminal worktrees.

## Validation evidence

Evidence recorded on 2026-07-28:

| Sequence | Failure injection | Expected semantic outcome | Durable evidence | Test |
|---|---|---|---|---|
| Claim then submit event | Stale generation | Reject event and preserve current state | SQLite run row | `test_stale_generation_cannot_transition` |
| Expire lease then restart | Controller loss | New generation and preserved old run | SQLite run and event rows | `test_restart_expires_lease_and_uses_higher_generation` |
| Evaluate candidate | Gate failure | Preserve candidate and base commit | Failed run and worktree | `test_gate_failure_prevents_promotion_and_preserves_worktree` |
| Evaluate committed candidate | Gate writes a file | Reject unverified mutation | Failed run and dirty worktree | `test_gate_mutation_prevents_promotion` |
| Promote candidate | Base moved | Refuse promotion | Git commits and raised invariant | `test_base_change_prevents_promotion` |
| Promote candidate | Git failure | Record terminal failure | SQLite failed run | `test_git_error_in_promotion_records_terminal_failure` |
| Configure manual promotion | Automatic promotion disabled | Stable handoff | Awaiting run and blocked item | `test_manual_promotion_policy_enters_stable_handoff` |
| Build child environment | Secret name is allowlisted | Exclude secret | Process environment assertion | `test_safe_environment_rejects_secret_name_even_if_allowed` |
| Record process text | Known secret forms present | Redact values | Redacted text assertion | `test_redact_text_removes_environment_and_known_token_shapes` |

Commands and outcomes:

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q`:
  21 tests passed.
- `python -m ruff check .`: passed.
- `PYTHONPATH=src python -m autobuild validate --skip-git-clean`: configuration,
  SPEC, executable, and Draft 2020-12 lifecycle-contract checks passed.

The environment-wide pytest plugin set caused an unbounded startup in the first
combined run. The isolated project test run disables unrelated plugin
autoloading. A fresh project virtual environment remains the supported setup.

## Uncertainties and assumptions

- The public repository has no license. This change does not add one.
- The portfolio has no curated or inventory record for this repository.
- The default Codex command is available in the current development
  environment. Other environments must install it or change the adapter.
- Full ASD-STE100 release evidence is unavailable. Project text is not released
  with a compliance claim.

## Blockers

None for the current implementation slice.

## Handoff

Status: implementation in progress.

Next owner and action: the autonomous orchestrator must add active lease
renewal, prove dispatch revalidation under injected SPEC or base movement, and
then dogfood repository validation and state inspection.
