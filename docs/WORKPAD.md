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
- [x] Add active lease renewal for agent and gate processes.
- [x] Prove dispatch rejection after a SPEC or base-commit change.
- [x] Dogfood validation and state inspection in this repository.
- [x] Run a live product reconciliation and preserve its failed adapter evidence.
- [x] Fix Windows command resolution and terminalize startup exceptions.
- [x] Fix deterministic source-checkout imports for isolated gates.
- [x] Add the automated controlled-English precheck and release boundary.
- [x] Add semantic cleanup for successful worktrees.
- [ ] Retry the live product reconciliation after the failed run lease expires.
- [ ] Run the first bounded self-improvement experiment.
- [ ] Add comparative improvement metrics for self-improvement work.

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
| Fresh read before dispatch and promotion | Required | `orchestrator.py`, `gitops.py` | SPEC-change, base-change, and Git integration tests | architecture | Proven for tested local boundaries |
| Active lease renewal and authority loss | Required | `process.py`, `state.py`, `orchestrator.py` | Heartbeat, renewal, and lost-authority tests | architecture, SECURITY | Proven |
| Shell-free gate execution | Required | `process.py` | Shell-injection negative | SECURITY | Proven |
| Deterministic Python gate environment | Required | `process.py`, `orchestrator.py` | Candidate source and pytest-isolation test | README, architecture | Proven |
| Secret containment and evidence redaction | Required | `process.py`, `orchestrator.py` | Environment and redaction negatives | SECURITY | Proven for configured and known forms |
| Candidate immutability after verification | Required | `orchestrator.py`, `gitops.py` | Gate-mutation negative | README, architecture | Proven |
| Isolated, fast-forward-only promotion | Required | `gitops.py` | Git integration tests | README, architecture | Proven |
| Successful-worktree cleanup | Required | `gitops.py`, `orchestrator.py` | Clean removal and dirty preservation tests | README, architecture, SECURITY | Proven |
| Bounded self-improvement | Required | normal work-item route | Pending | SPEC, architecture | Partial |
| Automated controlled-English precheck | Required | `writing.py`, CLI gate | Writing precheck tests and live command | README, writing standard | Proven for limited automated scope |
| Full STE claim requires human reviews | Required | repository policy and docs | Deterministic release labels | README, AGENTS, writing standard | Not released; human reviews unavailable |

Alignment review for `bootstrap-reconciler`:

- Required conflict repaired: the plan and handoff still marked implemented
  lease renewal, cleanup, and gate isolation as pending.
- Documentation-only drift repaired: two lifecycle proof names did not match
  the current test functions.
- Reviewed and unaffected: `SPEC.json` still defines the same acceptance
  criteria. README, architecture, security, setup, and examples remain accurate
  because this worker did not change runtime or security behavior.

## Implementation progress

The bootstrap reconciler provides a standard-library runtime and a Codex CLI
adapter. The controller renews leases during long child processes, commits a
candidate before evaluation, and rejects gate mutations. It cleans a verified
successful worktree after all semantic checks pass. It preserves failed,
stale, and manual-handoff worktrees.

The first live product run found a Windows command-resolution defect. Python
selected a restricted app-package executable instead of the npm command shim.
The fixed process runner resolves the explicit executable path before launch.
It also records future startup exceptions as terminal failures.

The second live product run recovered generation 1 and kept generation 2
current with lease heartbeats. The worker independently passed all checks and
made no changes. The controller gate then failed because its isolated
environment did not include the candidate source path. The fixed gate
environment supplies that path and disables ambient pytest plugin autoloading.

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
| Run long agent | Agent exceeds original lease | Renew authority and succeed | SQLite lease and succeeded run | `test_long_agent_renews_short_lease` |
| Run child process | Heartbeat loses authority | Stop child promptly | Exception and elapsed-time assertion | `test_process_stops_if_heartbeat_loses_authority` |
| Dispatch claimed item | SPEC changes after claim | Mark stale without worktree | SQLite stale run | `test_dispatch_stops_after_spec_change` |
| Dispatch claimed item | Base commit changes after claim | Mark stale without worktree | SQLite stale run and Git commit | `test_dispatch_stops_after_base_change` |
| Start agent process | Executable does not exist | Preserve worktree and record terminal failure | SQLite failed run | `test_agent_startup_error_records_terminal_failure` |
| Check configured Markdown | Long sentence or paragraph | Return a finding and block the gate | CLI and finding assertions | `test_writing.py` |
| Clean successful worktree | Dirty worktree | Preserve uncertain content | Git registry and path assertions | `test_cleanup_preserves_dirty_successful_worktree` |
| Run Python gate | Parent environment has no source path | Import candidate package deterministically | Environment assertion and full gate replay | `test_gate_environment_uses_candidate_source_and_isolated_pytest` |

Commands and outcomes:

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q`:
  34 tests passed.
- Focused lifecycle and security suite:
  27 tests passed.
- `python -m ruff check .`: passed.
- `PYTHONPATH=src python -m autobuild writing-check`: no automated
  findings; final status remained `NOT RELEASED — COMPLIANCE CHECK INCOMPLETE`.
- `PYTHONPATH=src python -m autobuild validate --skip-git-clean`: configuration,
  SPEC, executable, and Draft 2020-12 lifecycle-contract checks passed.
- `PYTHONPATH=src python -m autobuild validate`: the first read-only dogfood
  pass also confirmed a clean Git repository.
- `PYTHONPATH=src python -m autobuild status --json`: the real SQLite database
  projected both SPEC items and retained the failed live run evidence.
- Python process-runner probe: resolved `codex` to the npm command shim and
  returned `codex-cli 0.145.0`.
- Full configured-gate replay with the controller-created gate environment:
  tests, lint, repository validation, and writing precheck passed.

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
- Generation 1 is stale after its original lease expired. The pre-fix
  controller ended before it could record failure. The worktree and traceback
  remain preserved.
- Generation 2 is terminal failed with its clean candidate and gate output
  preserved. It proves lease recovery and exposed the source-path defect.

## Blockers

None for the current implementation slice.

## Handoff

Status: the `bootstrap-reconciler` implementation and its acceptance evidence
are complete at base commit `f8cb899566810f92d0df1d95190d2838fd4f9a5a`.

Next owner and action: the parent controller can run the configured gates and
apply its normal fast-forward promotion policy. The live product retry and the
first self-improvement experiment remain separate follow-up work.
