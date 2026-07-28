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
- [x] Retry the live product reconciliation after the failed run lease expires.
- [x] Run the first bounded self-improvement experiment.
- [x] Add baseline and candidate gate vectors for self-improvement work.
- [x] Bind achieved state to canonical work-item revisions.
- [x] Stop active children after desired-state or base-source authority loss.
- [x] Make malformed child output nonfatal and deterministic.
- [x] Add a renewable controller ownership lease.
- [x] Add bounded multi-candidate experiment ranking and promotion decisions.
- [ ] Add deterministic Git change-surface quality evidence.

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
| Item revision owns achieved state | Required | `spec.py`, `state.py` | Item identity and migration tests | README, architecture, lifecycle contract | Proven |
| SQLite owns leases and events | Required | `state.py` | State lifecycle tests | architecture | Proven for current local flow |
| Controller ownership fences scheduling and promotion | Required | `models.py`, `state.py`, `orchestrator.py` | Controller concurrency, renewal, stale-owner, and restart tests | README, architecture, SECURITY, lifecycle contract | Proven for local SQLite controllers |
| Generation fences stale events | Required | `state.py` | Stale and restart tests | lifecycle contract | Proven |
| Fresh read before dispatch and promotion | Required | `orchestrator.py`, `gitops.py` | SPEC-change, base-change, and Git integration tests | architecture | Proven for tested local boundaries |
| Active lease renewal and authority loss | Required | `models.py`, `process.py`, `state.py`, `orchestrator.py` | Full heartbeat, renewal, expiry, generation, and source-change tests | README, architecture, SECURITY, lifecycle contract | Proven for agent and gate callback paths |
| Shell-free gate execution | Required | `process.py` | Shell-injection negative | SECURITY | Proven |
| Deterministic bounded child output | Required | `process.py` | Invalid UTF-8 process-output test | README, SECURITY | Proven |
| Deterministic Python gate environment | Required | `process.py`, `orchestrator.py` | Candidate source and pytest-isolation test | README, architecture | Proven |
| Secret containment and evidence redaction | Required | `process.py`, `orchestrator.py` | Environment and redaction negatives | SECURITY | Proven for configured and known forms |
| Candidate immutability after verification | Required | `orchestrator.py`, `gitops.py` | Gate-mutation negative | README, architecture | Proven |
| Isolated, fast-forward-only promotion | Required | `gitops.py` | Git integration tests | README, architecture | Proven |
| Successful-worktree cleanup | Required | `gitops.py`, `orchestrator.py` | Clean removal and dirty preservation tests | README, architecture, SECURITY | Proven |
| Bounded self-improvement | Required | normal work-item route | Live generation 1 | SPEC, architecture | Proven for one local cycle |
| Measured self-improvement comparison | Required | baseline and candidate vectors with pass deltas | Improvement and unchanged-failure tests | README, SPEC, architecture, lifecycle contract | Promoted in `3a13e08` |
| Ranked self-improvement experiments | Required | `config.py`, `orchestrator.py`, `state.py` | Multi-candidate tie-break and candidate-timeout lifecycle tests | README, architecture, security, lifecycle contract | Proven for deterministic Boolean gate scores |
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

Alignment review for `recursive-improvement-cycle`:

- Implementation-defined omission repaired: self-improvement evaluation events
  now contain the observed gate vectors and numeric pass deltas.
- Required conflict repaired: an unchanged baseline and candidate gate failure
  is `no-improvement`, not `regression`.
- Reviewed and unaffected: `SPEC.json` already requires a measurable
  non-regression or improvement, so its product outcome does not change.
- Reviewed and unaffected: `SECURITY.md` remains accurate because the event uses
  the existing redacted gate results and adds only Boolean and integer values.
- Reviewed and unaffected: setup, version, provenance, release, and visual
  surfaces do not change. The existing execution-loop diagram remains accurate
  because this change refines evaluation evidence without changing control flow.

Alignment review for canonical work-item identity:

- Required drift repaired: achieved state used the full `SPEC.json` digest.
  Adding unrelated work could reopen every achieved item.
- Implementation and contract now use a canonical digest for each work item.
  The full file digest remains the dispatch and promotion fence.
- Migration behavior preserves an achieved legacy row only when its stored
  digest matches the currently observed full file.
- Reviewed and unaffected: `SPEC.json` content and acceptance criteria do not
  change in this checkpoint.
- Reviewed and unaffected: `SECURITY.md`, setup, adapter, promotion, cleanup,
  release, and writing-standard boundaries do not change.
- Visual meaning remains accurate. The architecture description now names both
  specification identities without changing the control-flow diagram.

Alignment review for the desired-state expansion:

- `SPEC.json` now requests active-run cancellation, controller ownership, and
  ranked self-improvement experiments.
- These items are desired work. The implementation does not claim that they
  are complete.
- Reviewed and unaffected: README and architecture limitations still describe
  the implemented controller and candidate-selection behavior.
- Reviewed and unaffected: security, setup, release, writing-standard, visual,
  and provenance claims do not change at this desired-state checkpoint.

Alignment review for `active-run-cancellation`:

- Required conflict repaired: child-process heartbeats renewed the SQLite lease
  without revalidating the full SPEC digest or base commit.
- Implementation-defined omission repaired: authority loss now records an
  `authority_lost` event with one cause from a bounded enumeration.
- Required evidence added: active SPEC and base-commit failure injections stop
  the agent before candidate creation, evaluation, or promotion.
- Documentation-only drift repaired: README, security, architecture, lifecycle
  contract, and execution-loop visual now describe all four heartbeat checks.
- Reviewed and unaffected: `SPEC.json` already defines the exact outcome and
  acceptance criteria, so its desired-state content does not change.
- Reviewed and unaffected: setup commands, adapter configuration, secret
  handling, cleanup, version, release, license, provenance, contribution, and
  support surfaces do not change because the patch only narrows runtime
  authority.

Alignment review for child-output decoding:

- Live controller-ownership generation 1 exposed locale-dependent decoding.
  A non-UTF-8 byte ended a reader thread and caused a secondary controller
  exception.
- The process runner now decodes UTF-8 with replacement. It also treats a
  missing captured stream as empty before it retains bounded text.
- README and security guidance now describe this process boundary.
- Reviewed and unaffected: SPEC, lifecycle states, adapter authority,
  promotion, cleanup, release, license, provenance, and visuals do not change.

Alignment review for `controller-ownership-lease`:

- Required conflict repaired: scheduling and promotion previously relied only
  on per-run leases and did not fence concurrent controller processes.
- The state database now binds one current controller owner token and
  generation to the resolved base repository. All scheduling mutations require
  that current controller lease.
- Promotion holds an immediate SQLite ownership transaction across the local
  Git fast-forward operation.
- Primary review repaired an uncovered lock-contention path. Schema
  initialization now maps SQLite `BUSY` or `LOCKED` to a deferred controller
  outcome while another controller holds the promotion transaction.
- Status and repository validation remain lease-free. Status no longer
  synchronizes desired state into SQLite.
- `SPEC.json` is reviewed and unaffected because it already defines this work
  item's objective and acceptance criteria.
- Setup commands remain valid. README now states the inspection-only status
  behavior.
- Release, license, provenance, contribution, support, adapter, process-output,
  secret-redaction, cleanup, and writing-standard surfaces are reviewed and
  unaffected because controller ownership does not change those contracts.
- The architecture visual now includes the controller lease and promotion
  ownership boundary.

Alignment review for `ranked-self-improvement-experiments`:

- Required conflict repaired: self-improvement previously created one candidate
  and had no configured candidate-count or per-candidate duration bound.
- Implementation-defined omission repaired: SQLite now stores each candidate's
  isolated source identity, complete gate vector, deterministic score, rank,
  eligibility, selection, and final promotion decision.
- Deterministic selection orders candidates by descending passed-gate count and
  then ascending candidate ID. Only an unchanged, all-pass, non-regressing
  candidate is eligible, and the database permits at most one selected row for
  each run.
- Primary review repaired a resource-policy omission. Configuration now
  rejects more than 8 candidates, more than 7200 seconds for one candidate, or
  more than 14400 configured candidate-seconds for one run.
- Documentation-only drift repaired: README, architecture, security, lifecycle
  behavior, and the execution-loop visual now describe bounded candidate
  fan-out, ranking, winner cleanup, and preserved non-winner worktrees.
- Reviewed and unaffected: `SPEC.json` already defines this work item and its
  acceptance criteria, so desired-state content does not change.
- Reviewed and unaffected: setup commands, adapter selection, secret redaction,
  controller ownership, release, license, provenance, contribution, support,
  and writing-standard boundaries do not change.
- Reviewed and unaffected: the lifecycle JSON schema still describes the same
  document structure. The instance changes only current behavior and evidence.

Alignment review for the quality-aware desired-state addition:

- `SPEC.json` now requests deterministic Git change-surface quality evidence.
- This item is desired work. The implementation does not claim that it is
  complete.
- The existing Boolean gate score remains the documented current limitation.
- Reviewed and unaffected: security, setup, adapter, controller, release,
  writing-standard, visual, license, and provenance claims do not change at
  this desired-state checkpoint.

## Implementation progress

The bootstrap reconciler provides a standard-library runtime and a Codex CLI
adapter. Each child-process heartbeat first revalidates the full SPEC digest
and base commit. It then renews controller ownership and validates the run
generation and run lease time. Authority loss stops the child, makes the run
stale, and records a bounded cause. The controller commits only under current
authority and rejects gate mutations. It cleans a verified successful worktree
after all semantic checks pass. It preserves failed, stale, and
manual-handoff worktrees.

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
| Capture child output | Invalid UTF-8 bytes | Replace malformed bytes and return a bounded result | Process result assertion | `test_process_replaces_invalid_utf8_output` |
| Run long agent | Agent exceeds original lease | Renew authority and succeed | SQLite lease and succeeded run | `test_long_agent_renews_short_lease` |
| Run child process | Heartbeat loses authority | Stop child promptly | Exception and elapsed-time assertion | `test_process_stops_if_heartbeat_loses_authority` |
| Run active agent | Full SPEC digest changes | Stop child before candidate evaluation or promotion | Stale run, bounded authority event, and preserved worktree | `test_active_agent_stops_after_spec_authority_loss` |
| Run active agent | Base commit changes | Stop child before candidate evaluation or promotion | Stale run, bounded authority event, and preserved worktree | `test_active_agent_stops_after_base_commit_authority_loss` |
| Renew active run | Generation differs | Reject heartbeat renewal | Typed bounded cause | `test_stale_generation_cannot_transition` |
| Renew active run | Lease time expired | Reject heartbeat renewal and preserve cause | Typed event and stale run | `test_expired_run_cannot_renew_lease`, `test_restart_expires_lease_and_uses_higher_generation` |
| Dispatch claimed item | SPEC changes after claim | Mark stale without worktree | SQLite stale run | `test_dispatch_stops_after_spec_change` |
| Dispatch claimed item | Base commit changes after claim | Mark stale without worktree | SQLite stale run and Git commit | `test_dispatch_stops_after_base_change` |
| Start agent process | Executable does not exist | Preserve worktree and record terminal failure | SQLite failed run | `test_agent_startup_error_records_terminal_failure` |
| Check configured Markdown | Long sentence or paragraph | Return a finding and block the gate | CLI and finding assertions | `test_writing.py` |
| Clean successful worktree | Dirty worktree | Preserve uncertain content | Git registry and path assertions | `test_cleanup_preserves_dirty_successful_worktree` |
| Run Python gate | Parent environment has no source path | Import candidate package deterministically | Environment assertion and full gate replay | `test_gate_environment_uses_candidate_source_and_isolated_pytest` |
| Evaluate self-improvement | Baseline fails and candidate passes | Record measurable improvement | Baseline and evaluation events | `test_self_improvement_records_baseline_and_improvement` |
| Evaluate unchanged failure | Baseline and candidate gate fail | Record zero delta and no improvement | Baseline and evaluation events | `test_self_improvement_does_not_call_an_unchanged_failure_a_regression` |
| Rank three candidates | Two eligible candidates have equal scores | Select candidate-001 and promote only it | Candidate rows, ranks, selection, promotion decision, and preserved non-winners | `test_self_improvement_ranks_candidates_and_promotes_deterministic_winner` |
| Exhaust candidate budgets | Both agents exceed the per-candidate duration | Record complete not-run gate vectors and refuse promotion | Timed-out candidate rows, rankings, no-eligible decision, and unchanged Git | `test_self_improvement_candidate_timeout_prevents_promotion` |
| Exceed experiment policy | Candidate count, one-candidate timeout, or aggregate candidate-seconds exceed a hard ceiling | Reject configuration before dispatch | Configuration error assertions | `test_config_requires_bounded_self_improvement_policy` |
| Record experiment evidence | Run generation differs | Reject the candidate evidence mutation | Empty candidate ranking projection | `test_stale_generation_cannot_change_experiment_evidence` |
| Add unrelated desired work | Full SPEC digest changes; item digest stays stable | Keep achieved item achieved | SQLite item state | `test_success_marks_item_achieved` |
| Change an achieved item | Canonical item digest changes | Return the item to ready | SQLite item state | `test_success_marks_item_achieved` |
| Migrate legacy identity | Stored item digest equals current full SPEC digest | Retain achieved state and store the item digest | SQLite digest and state | `test_sync_migrates_legacy_full_spec_digest_without_reopening` |
| Start two controllers | First controller lease remains current | Defer the second controller before run creation or promotion | Controller acquisition event and one run row | `test_concurrent_controller_cannot_dispatch_while_owner_is_current` |
| Start a controller during promotion | First controller holds the immediate ownership transaction | Map SQLite lock contention to a deferred outcome | Deferred outcome, one run row, and successful first promotion | `test_concurrent_controller_defers_during_promotion_transaction` |
| Replace a crashed controller | Prior controller lease expires | Acquire a higher controller generation and complete reconciliation | Controller acquisition generations and recovered run | `test_controller_restart_recovers_after_ownership_expiry` |
| Mutate with a stale controller | Another controller acquires after expiry | Reject state transition and promotion operation | SQLite controller row and typed rejection | `test_controller_lease_renews_and_fences_state_mutation` |
| Inspect status during ownership | Another controller lease remains current | Return status without acquiring or changing ownership | Controller lease status projection | `test_controller_lease_is_exclusive_and_recovers_after_expiry` |

Commands and outcomes:

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q`:
  35 tests passed.
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
- Live generation 3: all controller gates passed, commit `4263497` was promoted,
  the product item became achieved, and only the successful worktree was
  cleaned.

Candidate evidence recorded on 2026-07-28 for
`recursive-improvement-cycle`:

- The candidate started from commit
  `82659c60184b75b5417d8f80b2ad765055fa3a24` on registered worktree branch
  `autobuild/recursive-improvement-cycle/7cc302a6`.
- The focused comparison suite passed 2 tests. It measured an improvement
  delta of `+1` and an unchanged-failure delta of `0`.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src python -m pytest`:
  36 tests passed.
- `python -m ruff check .`: passed.
- `PYTHONPATH=src python -m autobuild writing-check`: no automated
  findings; final status remained `NOT RELEASED — COMPLIANCE CHECK INCOMPLETE`.
- `PYTHONPATH=src python -m autobuild validate --skip-git-clean`: configuration,
  SPEC, executable, and Draft 2020-12 lifecycle-contract checks passed.
- The controller committed the candidate before it ran the 4-of-4 passing gate
  vector and clean-state promotion check.
- The controller recorded the live baseline and candidate vectors as 4 of 4
  passed and classified the candidate as a non-regression.
- The controller promoted commit `3a13e08`, marked the self-improvement item
  achieved, and cleaned only the successful candidate worktree.

Canonical item-identity evidence recorded on 2026-07-28:

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src python -m pytest -q`:
  38 tests passed.
- `python -m ruff check .`: passed.
- Repository validation passed configuration, SPEC, executable, and Draft
  2020-12 lifecycle-contract checks.
- The automated writing precheck found no automated findings. Its final status
  remained `NOT RELEASED — COMPLIANCE CHECK INCOMPLETE`.
- Codeweb reported no new cycle, confirmed duplication, or lost caller.
- Before live migration, both achieved items stored the current full
  `SPEC.json` digest.
- Live status synchronization replaced those legacy values with two different
  canonical item digests. Both items remained achieved.

Active-run cancellation evidence recorded on 2026-07-28:

- The worktree started from commit
  `7aa640d174e072edcbffa5ab471beaf8fe790524`.
- The focused process, state, and orchestrator suite passed 29 tests.
- Both active source-authority failure injections passed three consecutive
  focused repetitions.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src python -m pytest -q`:
  40 tests passed.
- `python -m ruff check .`: passed.
- `PYTHONPATH=src python -m autobuild writing-check`: no automated findings;
  final status remained `NOT RELEASED — COMPLIANCE CHECK INCOMPLETE`.
- `PYTHONPATH=src python -m autobuild validate --skip-git-clean`: configuration,
  SPEC, executable, and Draft 2020-12 lifecycle-contract checks passed.
- `PYTHONPATH=src python -m autobuild validate`: all semantic checks passed;
  only the expected Git-clean check failed because this bounded worker must
  leave its implementation changes uncommitted for controller evaluation.
- Codeweb structural tools were unavailable because each local tool call was
  cancelled in the bounded worker. Direct diff review, lint, lifecycle schema
  validation, and the complete test suite supplied its available evidence.
- The controller promoted candidate `7a1ef5f` and cleaned its successful
  worktree.
- Primary review found that a failed source check preceded renewal but did not
  prevent it. The follow-up orders all source checks before lease renewal.
- The source-loss test now proves that the controller does not renew after a
  failed source check.
- Primary Codeweb review found no new cycle, confirmed duplication, or lost
  caller after the follow-up.

Controller-ownership generation 1 evidence recorded on 2026-07-28:

- Codex completed an uncommitted candidate in the isolated worktree.
- The Windows output reader failed on a locale-invalid byte in the Codex
  stream. The controller then recorded a terminal `TypeError`.
- The run is failed. Its worktree, candidate changes, result summary, and
  durable SQLite evidence remain preserved.
- The base repository stayed clean at commit `f1b6e4f`.
- The decoding regression test emits invalid bytes on both output streams.
- The focused process suite passed 8 tests, and the full suite passed 41 tests.
- Ruff, repository validation, lifecycle schema validation, and the writing
  precheck passed.
- Codeweb found no new cycle, confirmed duplication, or lost caller.

Controller ownership lease implementation evidence recorded on 2026-07-28:

- This bounded worker started from
  `6d4fd2771c7e4f2d3e258cfbb9cb11d7739c66fc`.
- The focused state, orchestrator, validation, and configuration suite passed
  28 tests.
- `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest` passed all
  46 tests.
- The exact unconfigured `python -m pytest` command could not import the
  `src`-layout package because this worktree is not installed in the ambient
  Python environment. The supported source-path run passed.
- `python -m ruff check .` passed.
- `PYTHONPATH=src python -m autobuild writing-check` found no automated
  findings. Its final status remained
  `NOT RELEASED — COMPLIANCE CHECK INCOMPLETE`.
- `PYTHONPATH=src python -m autobuild validate --skip-git-clean` passed
  configuration, SPEC, executable, and Draft 2020-12 lifecycle-contract
  checks.
- `PYTHONPATH=src python -m autobuild status --json` projected all desired
  items and left the state database modification time unchanged.
- Codeweb structural calls were unavailable because the bounded worker tool
  calls were cancelled. Direct diff review, Ruff, lifecycle schema validation,
  and the complete test suite provide the available structural evidence.
- The controller promoted generation 2 as commit `b915668` and cleaned its
  successful worktree.
- Primary Codeweb review found no new cycle, confirmed duplication, or lost
  non-exported caller in the promoted candidate.
- Primary review added promotion-overlap failure injection. A second controller
  now defers if schema initialization meets the active SQLite transaction.
- Primary review also corrected lifecycle text to match the implemented
  source-check, controller-renewal, and run-check order.
- The post-review suite passed 47 tests. Ruff, repository validation, lifecycle
  schema validation, and the writing precheck passed.
- Post-review Codeweb analysis found no new cycle, confirmed duplication, or
  lost caller.

Ranked self-improvement implementation evidence recorded on 2026-07-28:

- This bounded worker started from
  `511c35a6deb164076f3d6c51f3517ac927e8595b`.
- `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q`
  passed all 52 tests.
- `python -m ruff check .` passed.
- `PYTHONPATH=src python -m autobuild writing-check` found no automated
  findings. Its final status remained
  `NOT RELEASED — COMPLIANCE CHECK INCOMPLETE`.
- `PYTHONPATH=src python -m autobuild validate --skip-git-clean` passed
  configuration, SPEC, executable, and Draft 2020-12 lifecycle-contract
  checks.
- The exact clean-tree validation passed every semantic check. It reported only
  the expected `git-clean` failure because this worker must leave the candidate
  uncommitted for controller evaluation.
- The structural mapping call was cancelled before a graph was created. Direct
  call-site review, the complete lifecycle suite, Ruff, schema validation, and
  diff checks provide the available structural evidence.
- Pytest emitted the known ignored Windows permission warning while its exit
  cleanup inspected an ambient temporary-directory link. The test command
  returned success and did not change repository files.
- The controller promoted commit `6ca252d` and cleaned its successful worktree.
- The live state database recorded controller acquisition and release for
  generation 1 and the resolved repository. Status reports that lease inactive.
- This bootstrap cycle ran the prior single-candidate controller code. The new
  candidate-ranking tables are therefore empty for that cycle. A later
  self-improvement run must dogfood the multi-candidate path.
- Primary review added hard candidate-count, per-candidate duration, and
  aggregate candidate-seconds ceilings.
- The post-review suite passed 52 tests. Ruff, repository validation, lifecycle
  schema validation, and the writing precheck passed.
- Primary Codeweb review found no new cycle, confirmed duplication, or lost
  caller.

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
- Controller-ownership generation 1 is terminal failed. Its uncommitted
  candidate remains preserved after the child-output decoding defect.
- Pytest passed all tests but emitted an ignored Windows permission warning
  while its process-exit cleanup inspected an ambient temporary-directory
  link. The warning did not change the test exit status or repository files.

## Blockers

None for the current implementation slice.

## Handoff

Status: ranked experiments and hard resource ceilings are pushed. The
quality-aware ranking item is ready.

Next owner and action: push this desired-state checkpoint, then run the first
live multi-candidate reconciliation.
