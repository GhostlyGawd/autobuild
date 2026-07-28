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
- [x] Add deterministic Git change-surface quality evidence.
- [x] Reconcile interrupted local Git promotions.
- [x] Make unsafe repository artifacts candidate-local and ineligible.

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
| Ranked self-improvement experiments | Required | `config.py`, `orchestrator.py`, `state.py` | Multi-candidate tie-break and candidate-timeout lifecycle tests | README, architecture, security, lifecycle contract | Proven for fan-out, eligibility, and preservation; quality ranking is below |
| Git change-surface quality ranking | Required | `models.py`, `gitops.py`, `orchestrator.py`, `state.py` | Git metric, tampering, unequal-quality, exact-tie, and legacy-status tests | README, architecture, security, lifecycle contract | Proven by two three-candidate live runs, including the current controller |
| Promotion crash recovery | Required | immutable intent and fenced recovery in `state.py` and `orchestrator.py`; existing exact Git observations in `gitops.py` | before-Git, after-Git, post-success, divergence, stale-authority, stale-controller, and idempotent-restart tests | SPEC, README, architecture, SECURITY, lifecycle contract | Normal-path live intent proven; injected process-death recovery remains test-only |
| Artifact-safe candidate eligibility | Required | typed staging rejection in `gitops.py`; candidate-local disposition in `orchestrator.py`; bounded evidence validation in `state.py` | multiple-Gitlink staging, one-unsafe-one-valid, all-unsafe, and invalid-evidence tests | SPEC, README, architecture, SECURITY, lifecycle contract | Implementation promoted live; outer live artifact injection remains pending |
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

Alignment review for `quality-aware-ranking`:

- Required conflict repaired: eligible self-improvement candidates previously
  ranked by Boolean gate-pass score instead of committed Git change surface.
- The controller now measures changed files, insertions, deletions, and total
  changed lines from the claimed base to each candidate commit. All gates,
  non-regression checks, authority checks, and mutation checks remain required.
- SQLite now stores constrained immutable quality vectors, recomputes
  deterministic ranks, permits one selected row, and verifies that later
  promotion decisions still refer to the selected candidate commit and quality
  evidence.
- Eligible candidates rank by fewer changed lines, fewer changed files, and
  ascending candidate ID. Failure injections cover inconsistent metrics,
  direct SQLite tampering, unequal quality, and exact ties.
- Documentation-only drift repaired: README, architecture, security, lifecycle
  behavior, lifecycle evidence, and the control-flow visual now describe the
  Git quality vector and selection rule.
- Reviewed and unaffected: `SPEC.json` already owns the exact objective and
  acceptance criteria, so desired-state content does not change.
- Reviewed and unaffected: setup, adapter selection, controller leases, process
  isolation, secret redaction, cleanup, writing-standard, release, version,
  license, provenance, contribution, and support boundaries do not change.
- Reviewed and unaffected: the lifecycle schema remains accurate because the
  instance adds evidence within the existing document structure.
- Primary review repaired a required upgrade conflict. Read-only status hid
  existing candidate and promotion rows when a pre-upgrade database did not
  yet contain the new quality table. Status now returns those rows with null
  quality fields and does not mutate the database.
- `test_status_reads_state_without_experiment_tables` and
  `test_status_preserves_legacy_experiment_evidence_before_migration` prove
  the read-only fallbacks, preserved rank and selection, preserved promotion
  decision, and absence of an implicit schema mutation.

Alignment and plan contract for `promotion-crash-recovery`:

- Current workflow: the persistent controller stores `promoting`, fast-forwards
  the base repository, then records run success and the final promotion
  decision. A process crash after Git succeeds but before SQLite finalization
  leaves durable systems in disagreement.
- Present problem: lease expiry can mark that run stale and return the work
  item to ready even though the intended candidate is already the base commit.
  A later controller can duplicate work and the promotion decision can remain
  incomplete.
- Direction and benefit: store an immutable promotion intent before the Git
  boundary. A replacement controller uses that intent, current SPEC, current
  Git, and a fresh controller lease to finalize the exact already-applied
  commit once. Autonomous progress then survives this crash without owner
  recovery work or an unsafe overwrite.
- The existing approach remains sufficient when the controller cannot crash
  during promotion. The added state is justified because this harness is
  explicitly long-running and autonomous.
- Alternatives rejected: doing nothing preserves the inconsistency window.
  A distributed transaction coordinator adds an external system with no
  current consumer and cannot make local Git and SQLite one atomic resource.
- Authority: `SPEC.json` owns the desired outcome, Git owns applied source,
  SQLite owns the immutable intent and lifecycle, and the current controller
  lease owns recovery mutation. Current SPEC and Git observations take
  precedence over stale intent.
- State contract:
  - Expected base still current after a pre-Git crash: expire the run to
    retryable state and preserve the worktree.
  - Base equals the intended candidate after a post-Git crash: finalize the
    run, achievement, and promotion decision exactly once.
  - Base is an unrelated commit or SPEC authority changed: do not overwrite
    source; record a bounded stale or conflict outcome and preserve evidence.
  - Run is already successful but its decision is incomplete: repair only the
    matching decision; repeated recovery has no additional effect.
- Planned responsibilities: `state.py` owns intent schema, immutability,
  fenced reconciliation, and status. `orchestrator.py` records intent before
  Git and invokes recovery before new claims. `gitops.py` supplies exact commit
  checks. State, Git, and orchestrator tests own the crash matrix.
- Required proof: inject crashes before Git, after Git, and after run success;
  inject unrelated base movement and stale controller authority; restart more
  than once; prove no duplicate promotion, no overwrite, exact achievement,
  repaired self-improvement decision, and preserved uncertain worktrees.
- Live proof: the next three-candidate self-improvement run must select with
  committed Git change-surface evidence. It can prove normal promotion intent
  behavior, but synthetic crash injections remain the authoritative evidence
  for process-death windows.
- In scope: local fast-forward promotion and local SQLite recovery. Out of
  scope: remote push, distributed controllers, external transaction services,
  automatic continuation of a pre-Git candidate, and cleanup of uncertain
  preserved worktrees.
- Documentation impact: implementation must reconcile README, architecture and
  its control-flow visual, SECURITY, lifecycle evidence, the alignment table,
  and dated live evidence. Setup, adapter, writing-release, license,
  provenance, contribution, and support claims are reviewed but are not
  expected to change.
- The owner explicitly delegated direction and implementation authority to the
  orchestrator for this build. That standing decision approves this bounded
  direction and plan contract.
- Desired-state checkpoint evidence recorded on 2026-07-28: the focused SPEC,
  state, and validation suite passed all 20 tests; repository validation
  accepted 7 work items and the lifecycle schema; the writing precheck found
  no automated findings and retained its non-release label.
- Reviewed and unaffected at this checkpoint: runtime, configuration, setup,
  adapter, security, architecture, visuals, lifecycle behavior, examples,
  version, readiness, license, provenance, contribution, and support claims do
  not change until a candidate is promoted.

Alignment review for `promotion-crash-recovery` implementation:

- Required conflict repaired: Git could reach the selected candidate while the
  durable run remained `promoting`.
- Implementation-defined omission repaired: SQLite now stores a write-once
  intent before Git changes the base. The intent binds the run generation,
  expected base, candidate commit, worktree, full SPEC digest, and canonical
  work-item digest.
- Required recovery behavior added: a current replacement controller repairs
  the run, item achievement, and self-improvement decision in one SQLite
  transaction only when the base is the exact candidate and both SPEC
  identities remain current.
- Required refusal behavior added: an unchanged base makes the run retryable.
  A divergent base or stale SPEC authority records refusal. Recovery does not
  run Git and preserves the worktree.
- Documentation-only drift repaired: README, architecture, security guidance,
  lifecycle behavior, and the control-flow visual now show the intent and
  restart decision.
- Reviewed and unaffected: `SPEC.json` already defines the objective and exact
  acceptance criteria. Setup, configuration, adapter, writing-release, version,
  readiness, license, provenance, contribution, and support behavior do not
  change.
- Completion state: self-contained worker change. No external gate, remote
  mutation, or post-merge evidence is required for handoff. Live dogfood is
  separate dated evidence and does not replace the failure-injection matrix.
- Worker evidence recorded on 2026-07-28: the full repository suite passed 64
  tests; Ruff passed the full tree; the automated writing precheck reported no
  findings and retained its non-release label; lifecycle Draft 2020-12 schema
  validation passed. Repository validation also passed configuration, SPEC,
  and executable checks. Its `git-clean` check remains open because this
  bounded worker handoff intentionally contains uncommitted changes.

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
| Rank three candidates | Two eligible candidates have exact quality ties | Select candidate-001 and promote only it | Quality vectors, ranks, selection, promotion decision, and preserved non-winners | `test_self_improvement_ranks_candidates_and_promotes_deterministic_winner` |
| Measure committed candidate | One file is replaced and one file is added | Count two files, three insertions, one deletion, and four changed lines | Git comparison result | `test_committed_change_surface_counts_files_and_lines` |
| Rank unequal quality | Eligible candidates have unequal line and file counts | Rank fewer lines first and fewer files second | Quality vectors, ranks, selection, and promoted commit | `test_self_improvement_ranks_unequal_quality_before_candidate_id` |
| Record tampered metric | Changed lines differ from insertions plus deletions | Reject the vector before ranking or promotion | Failed run, SQLite constraint, absent rank, and absent decision | `test_quality_metric_tampering_prevents_ranking_and_promotion`, `test_sqlite_rejects_quality_metric_tampering` |
| Exhaust candidate budgets | Both agents exceed the per-candidate duration | Record complete not-run gate vectors and refuse promotion | Timed-out candidate rows, rankings, no-eligible decision, and unchanged Git | `test_self_improvement_candidate_timeout_prevents_promotion` |
| Stage one unsafe and one valid candidate | Candidate 1 adds a nested repository | Reject candidate 1 without gates or quality, continue candidate 2, and promote only candidate 2 | Bounded rejection event and row, preserved rejected worktree, valid quality vector, selection, and promotion | `test_self_improvement_rejects_unsafe_candidate_and_promotes_later_candidate` |
| Stage only unsafe candidates | Every candidate adds a nested repository | Reject all candidates and refuse promotion | Bounded rejection rows and events, null gate and quality evidence, deterministic ranks, no intent, unchanged Git, and preserved worktrees | `test_all_artifact_rejected_candidates_preserve_evidence_without_promotion` |
| Exceed experiment policy | Candidate count, one-candidate timeout, or aggregate candidate-seconds exceed a hard ceiling | Reject configuration before dispatch | Configuration error assertions | `test_config_requires_bounded_self_improvement_policy` |
| Record experiment evidence | Run generation differs | Reject the candidate evidence mutation | Empty candidate ranking projection | `test_stale_generation_cannot_change_experiment_evidence` |
| Read legacy database | Experiment tables or only the quality table are absent | Return available legacy evidence with null quality fields and do not migrate state | Empty or preserved projections and unchanged SQLite schema | `test_status_reads_state_without_experiment_tables`, `test_status_preserves_legacy_experiment_evidence_before_migration` |
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

Quality-aware ranking implementation evidence recorded on 2026-07-28:

- This bounded worker started from
  `48bc7ca7a1a94446b031163332fc72d8be37c3bd`.
- The five focused change-surface, tampering, unequal-quality, and exact-tie
  tests passed.
- The focused Git, state, and orchestrator suite passed all 38 tests.
- `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q`
  passed all 56 tests.
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
- Codeweb mapping, context, impact, similarity, placement, refresh, and diff
  calls were cancelled before a graph was available. Direct call-site review,
  the full lifecycle suite, Ruff, schema validation, and diff checks provide
  the available structural evidence.
- Pytest emitted the known ignored Windows permission warning while its exit
  cleanup inspected an ambient temporary-directory link. The test command
  returned success and did not change repository files.

Quality-aware ranking live dogfood and primary-review evidence recorded on
2026-07-28:

- Run `0e5bf135-949b-4a4e-a923-970202fd218d` started three isolated candidates
  from `48bc7ca7a1a94446b031163332fc72d8be37c3bd`.
- Candidate 1 produced `394e63e`, candidate 2 produced `fa8abea`, and candidate
  3 produced `b43bce8`. Each candidate passed all four controller gates and
  was eligible.
- The bootstrap controller ranked the exact Boolean-gate tie by ascending
  candidate ID. It promoted candidate 1 as `394e63e`, cleaned only the winner
  worktree, and preserved candidate 2 and candidate 3 worktrees.
- The promoted checkpoint was pushed to
  `origin/agent/bootstrap-autobuild`.
- This run proves bounded fan-out, isolation, controller-gate replay,
  deterministic prior-policy ranking, one-winner promotion, winner cleanup,
  and non-winner preservation. It does not prove live Git change-surface
  ordering because the running controller predated that behavior.
- Primary review reproduced a read-only upgrade defect against the live state
  database: status returned zero candidate and promotion rows before the
  quality table existed. The repaired projection returns all three ranked
  candidates and the promotion decision with null quality fields, and it
  leaves the database schema unchanged.
- The focused state suite passed all 16 tests after the repair.
- Codeweb refresh and diff found no new cycle, confirmed duplication, or lost
  caller after the primary repair.
- The full isolated post-review suite passed all 58 tests. Ruff passed.
- Repository validation passed configuration, SPEC, executable, and Draft
  2020-12 lifecycle-contract checks. Exact validation reported only the
  expected dirty-tree failure before the primary repair commit.
- The writing precheck found no automated findings and retained
  `NOT RELEASED — COMPLIANCE CHECK INCOMPLETE`.

Promotion crash-recovery live dogfood and primary-review evidence recorded on
2026-07-28:

- Run `3147e6e0-bedb-4837-bd59-08562bb56ebd` started three isolated candidates
  from `86ce851e511db8379b13cf4154ce35bdddeaae62`.
- Candidate 1 produced `a5e91bc`, candidate 2 produced `68e8753`, and candidate
  3 produced `76483cc`. Each candidate passed all four controller gates and
  was eligible.
- SQLite recorded immutable quality vectors of 1,139 changed lines across 10
  files for candidate 1, 1,359 lines across 10 files for candidate 2, and 902
  lines across 22 files for candidate 3. It ranked the candidates as 3, 1, 2
  and promoted candidate 3.
- Candidate 3 accidentally committed a pytest temporary tree. The tree
  included generated nested repositories as Gitlinks. Binary and Gitlink
  entries added few lines to the quality vector, so the line-first proxy did
  not reject the artifact-heavy candidate.
- Winner cleanup failed with `working trees containing submodules cannot be
  moved or removed`. The controller preserved that worktree. It also preserved
  both non-winning worktrees.
- Primary review removed the promoted temporary tree. It added a candidate
  commit guard that rejects newly added Gitlinks and a root ignore rule for
  `pytest-of-*` temporary trees.
- Primary review extended the post-Git crash test. The test now proves that an
  unrelated uncommitted base change defers recovery and leaves the run in
  `promoting` until the base is clean.
- The running controller predated promotion-intent support. It could promote
  the recovery implementation, but it could not record or exercise a
  `promotion_intents` row. This run proves live quality-aware ordering. It does
  not prove live restart recovery.
- The promoted autonomous checkpoint `76483cc` was pushed to
  `origin/agent/bootstrap-autobuild` before primary review.
- Primary review removed 13 generated entries: one SQLite test database, five
  Gitlinks, and seven temporary-directory links. The failed winner cleanup left
  its managed worktree intact for later semantic cleanup.
- The focused Git and post-Git recovery suite passed all 6 tests.
- The complete isolated suite passed all 65 tests. Ruff passed.
- Repository validation passed configuration, SPEC, executable, and Draft
  2020-12 lifecycle-contract checks.
- The writing precheck found no automated findings and retained
  `NOT RELEASED — COMPLIANCE CHECK INCOMPLETE`.
- Codeweb refresh and diff found no new cycle, confirmed duplication, orphaned
  symbol, or lost caller.
- Documentation drift was behavioral, security, architecture, lifecycle, and
  dated-evidence drift. README, SECURITY, architecture, lifecycle JSON, and
  this workpad were aligned in the same change. `SPEC.json`, configuration,
  setup commands, agent adapters, version claims, and release boundaries were
  reviewed and remain unaffected because the repair changes only candidate
  staging safety and test coverage.

Artifact-safe candidate eligibility alignment and plan recorded on 2026-07-28:

- Present problem: live run `3147e6e0-bedb-4837-bd59-08562bb56ebd` selected an
  artifact-heavy candidate because generated Gitlinks and a binary database
  added few changed lines. The promoted Gitlinks then blocked winner cleanup.
- Current workflow: `commit_candidate` now rejects a newly added Gitlink, but
  its `GitError` leaves the per-candidate loop. One unsafe candidate therefore
  fails the complete self-improvement run and prevents later candidates from
  being evaluated.
- Present consumer: the multi-candidate self-improvement controller needs
  candidate-local rejection so one generated nested repository cannot suppress
  an otherwise valid candidate. If this work is omitted, one unsafe first
  candidate can waste the full bounded experiment and prevent a valid winner.
- Rejected direction: an ignore rule alone is path-specific and cannot cover an
  arbitrary generated nested repository.
- Approved direction: catch the staging rejection at the candidate boundary,
  record one bounded artifact-rejection classification, preserve its worktree,
  and continue with the remaining candidates. Only committed candidates can
  run gates or receive immutable quality evidence.
- Deferred direction: binary byte size or general artifact-size weighting is a
  future quality-policy option. It is not required to close the observed
  Gitlink failure.
- Acceptance tests will inject one unsafe candidate followed by one valid
  candidate, then inject an all-unsafe run. They will verify classification,
  missing gate and quality evidence for unsafe candidates, valid-candidate
  promotion, no-promotion behavior, and rejected-worktree preservation.
- Implementation surfaces: orchestrator candidate staging, bounded candidate
  classifications, Git isolation tests, lifecycle failure injections, README,
  SECURITY, architecture, and this workpad. Configuration, setup, adapters,
  versions, and external integrations are unaffected.
- The owner's standing autonomous-build direction satisfies the direction and
  implementation approval gates for this bounded local change.

Artifact-safe candidate eligibility implementation evidence recorded on
2026-07-28:

- Required conflict repaired: a Gitlink staging failure no longer escapes the
  self-improvement candidate boundary and aborts later candidates.
- Implementation-defined omission repaired: SQLite now validates the bounded
  `artifact-rejected` evidence shape. The rejected row has no candidate commit,
  gate execution, quality vector, eligibility, or selection authority.
- Required cleanup behavior proven: the controller cleans only the promoted
  winner. It preserves each rejected worktree and its nested repository.
- Failure injection proves one unsafe candidate followed by one valid winner.
  It also proves that an all-unsafe run records `no-eligible-candidate`, creates
  no promotion intent, and does not change Git.
- Documentation-only drift repaired: README, SECURITY, architecture, lifecycle
  failure boundaries, failure-injection evidence, and this workpad now describe
  candidate-local artifact rejection and preservation.
- Reviewed and unaffected: `SPEC.json` already defines the exact outcome and
  acceptance criteria. Configuration, setup commands, agent adapters, versions,
  licensing, provenance, releases, and external integrations do not change.
- The four new or extended acceptance tests passed.
- The focused Git, state, and orchestrator suite passed all 50 tests.
- The complete isolated suite passed all 68 tests.
- Ruff and `git diff --check` passed.
- Repository validation passed configuration, SPEC, executable, and Draft
  2020-12 lifecycle-contract checks with `--skip-git-clean`. Exact validation
  reported only the expected dirty-tree failure because this bounded worker
  must leave the candidate uncommitted.
- The writing precheck found no automated findings and retained
  `NOT RELEASED — COMPLIANCE CHECK INCOMPLETE`.
- Codeweb mapping, pre-edit context, similarity, placement, refresh, and diff
  calls were unavailable because the local tool calls were cancelled. Direct
  call-site review, the complete lifecycle suite, Ruff, schema validation, and
  diff checks provide the available structural evidence.
- Pytest emitted the known ignored Windows permission warning while its
  process-exit cleanup inspected an ambient temporary-directory link. The test
  command returned success and did not change repository files.

Artifact-safe candidate eligibility live promotion and primary-review evidence
recorded on 2026-07-28:

- Run `95b919c0-0f47-498d-83bb-eeb19c09200a` started three isolated candidates
  from `57104ac50d74769fdcb35fcd272d0965fa11e14f`.
- Candidate 1 produced `fef003d`, candidate 2 produced `0732079`, and candidate
  3 produced `bbe3db8`. Each candidate passed all four controller gates and
  was eligible.
- SQLite recorded quality vectors of 511 changed lines across 11 files for
  candidate 1, 500 changed lines across 11 files for candidate 2, and 468
  changed lines across 11 files for candidate 3. The controller ranked the
  candidates as 3, 2, 1 and promoted candidate 3.
- Before Git changed the base, SQLite stored the run, expected base, candidate
  commit, winner worktree, full SPEC digest, and work-item digest in one
  immutable promotion-intent row. The promotion decision names the same
  candidate and commit.
- The controller cleaned the promoted winner worktree after success. It
  preserved the candidate 1 and candidate 2 worktrees. The promoted checkpoint
  `bbe3db8` was pushed to `origin/agent/bootstrap-autobuild`.
- This live run proves current-controller gate replay, Git change-surface
  ranking, normal-path intent creation, one-winner promotion, winner cleanup,
  and non-winner preservation. The outer controller candidates were safe. The
  mixed and all-unsafe failure-injection tests remain the evidence for actual
  artifact rejection.
- Primary review found that SQLite enforced the artifact-rejection shape only
  when the classification already equaled `artifact-rejected`. A caller could
  supply status `rejected` with another classification or rewrite a stored
  rejection as another candidate state.
- Primary review now restricts candidate status and classification values,
  requires the exact paired artifact-rejection shape from either direction,
  and prevents a stored artifact rejection from becoming another disposition.
- Documentation drift was behavioral, state-integrity, security, architecture,
  lifecycle, and dated-evidence drift. README, SECURITY, architecture,
  lifecycle JSON, and this workpad were aligned in the same change.
- Reviewed and unaffected: `SPEC.json` already defines the required outcome and
  acceptance criteria. Configuration, setup commands, agent adapters, versions,
  licensing, provenance, releases, and external integrations do not change.
- The focused state, Git, and orchestrator suite passed all 8 tests.
- The complete isolated suite passed all 68 tests. Ruff and
  `git diff --check` passed.
- Repository validation passed configuration, SPEC, executable, and Draft
  2020-12 lifecycle-contract checks with `--skip-git-clean`.
- The writing precheck found no automated findings and retained
  `NOT RELEASED — COMPLIANCE CHECK INCOMPLETE`.
- Codeweb refresh and diff retained 207 symbols and 257 edges. It found no new
  cycle, confirmed duplication, orphan, or lost caller.

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

Status: artifact-safe candidate eligibility is promoted and live-ranked. The
primary state-integrity repair passed the complete local validation set and is
ready for its checkpoint commit.

Next owner and action: after the primary repair is pushed, a later bounded
self-improvement run can inject an actual unsafe outer candidate. A later
controlled process-death run can provide live restart-recovery evidence.
