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
- [ ] Prove the full lifecycle and security matrix with deterministic tests.
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
| SPEC owns desired state | Required | `spec.py`, `orchestrator.py` | Pending | README, architecture | Implemented; test pending |
| SQLite owns leases and events | Required | `state.py` | Pending | architecture | Implemented; test pending |
| Generation fences stale events | Required | `state.py` | Pending | lifecycle contract | Implemented; test pending |
| Fresh read before dispatch and promotion | Required | `orchestrator.py` | Pending | architecture | Implemented; test pending |
| Shell-free gate execution | Required | `process.py` | Pending | SECURITY | Implemented; test pending |
| Isolated, fast-forward-only promotion | Required | `gitops.py` | Pending | README, architecture | Implemented; test pending |
| Bounded self-improvement | Required | normal work-item route | Pending | SPEC, architecture | Partial |
| Full STE claim requires human reviews | Required | repository policy and docs | Text audit pending | README, AGENTS | Implemented; not released as compliant |

## Implementation progress

The first implementation slice provides a standard-library runtime and a
Codex CLI adapter. The controller preserves failed or stale worktrees. It does
not yet renew an active lease or clean terminal worktrees.

## Validation evidence

No post-implementation validation has been recorded yet.

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

Next owner and action: the autonomous orchestrator must add lifecycle tests,
run all validation commands, record dated evidence here, and then select the
next unproved acceptance criterion.

