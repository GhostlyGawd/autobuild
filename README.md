# autobuild

`autobuild` is a local-first harness for autonomous engineering. It converts a
version-controlled specification into fenced, resumable work. It runs an agent
in an isolated Git worktree, evaluates the result, and promotes only a verified
commit.

Status: early development. The control loop and safety contracts are usable,
but the project is not production-ready.

## What it does

- Keeps desired outcomes in `SPEC.json`.
- Uses a canonical digest for each work item to retain unrelated achievements.
- Uses the full `SPEC.json` digest to fence each active run.
- Keeps execution state and evidence in SQLite.
- Uses a renewable controller owner token and generation for each state database
  and resolved base repository.
- Defers a second controller while the current controller ownership lease is
  valid.
- Reconciles desired state instead of trusting a worker process.
- Uses lease generations to reject stale worker events.
- Revalidates the full SPEC digest, base commit, lease generation, and lease
  time at each active child-process heartbeat.
- Renews the lease only while all heartbeat authority checks pass.
- Stops the child process and records a bounded cause if heartbeat authority
  is lost.
- Runs agents in isolated Git worktrees.
- Commits a candidate before it runs verification gates.
- Rejects newly added Gitlinks before it creates a candidate commit. A rejected
  self-improvement candidate keeps bounded evidence and its worktree. It cannot
  run gates or receive a quality vector, and later candidates continue. SQLite
  rejects unknown candidate states and does not let an artifact rejection
  become a different candidate disposition.
- Runs verification gates without a command shell.
- Decodes child output as UTF-8 with replacement and retains bounded text.
- Gives Python gates the candidate `src` path and disables ambient pytest
  plugin autoloading.
- Rejects a candidate if a gate changes the committed content.
- Revalidates the SPEC and base commit before dispatch and promotion.
- Stores a write-once promotion intent with the run, expected base, candidate
  commit, worktree, and SPEC identities before it changes the base repository.
- Holds the SQLite controller-ownership transaction while it performs local
  promotion.
- Lets a replacement controller finalize an exact already-applied promotion
  under current SPEC and controller authority.
- Cleans a successful worktree only after reachability, path, registration, and
  clean-state checks pass.
- Bounds self-improvement with a configured candidate count and a configured
  combined agent-and-gate process-time budget for each candidate.
- Starts each self-improvement candidate from the same base commit in a
  separate worktree.
- Records baseline and candidate gate vectors, Git change-surface vectors,
  deterministic ranks, and the promotion decision in SQLite.
- Selects only an all-pass, non-regressing candidate. Eligible candidates rank
  by fewer changed lines, fewer changed files, and ascending candidate ID.
  The controller promotes at most one candidate.
- Treats automated controlled-English checks as evidence, not as an
  ASD-STE100 compliance decision.

## Five-minute setup

Requirements:

- Python 3.11 or later
- Git
- Codex CLI for live agent runs

```text
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\autobuild validate
.venv\Scripts\autobuild status
```

On macOS or Linux, use `.venv/bin/python` and `.venv/bin/autobuild`.
The `status` command inspects current state without acquiring controller
ownership or synchronizing desired state into SQLite.

Run one reconciliation cycle:

```text
autobuild run --once
```

The default configuration uses `codex exec` with workspace-write sandboxing.
Review `.autobuild/config.toml` before the first live run. A successful agent
process is not sufficient for promotion. All configured gates must pass, and
they must leave the candidate unchanged.

The `[self_improvement]` table sets `max_candidates` and
`candidate_timeout_seconds`. The timeout bounds the combined child-process
time for the agent and gates of each candidate. The default policy evaluates
at most three candidates and gives each candidate at most 3600 seconds.
The runtime permits at most 8 candidates, at most 7200 seconds for one
candidate, and at most 14400 configured candidate-seconds for one run.

## Project contract

- [`SPEC.json`](SPEC.json) defines the desired outcomes and acceptance checks.
- [`docs/WORKPAD.md`](docs/WORKPAD.md) records the current build state and
  validation evidence.
- [`docs/reconciled-agent-loop.json`](docs/reconciled-agent-loop.json) defines
  lifecycle ownership, recovery, and cleanup.
- [`docs/architecture.md`](docs/architecture.md) explains the system flow and
  current limitations.
- [`SECURITY.md`](SECURITY.md) defines the trust and containment boundaries.

Each work item has a SHA-256 digest of its canonical JSON object. The state
store uses this digest to decide if an achieved item changed. A change to a
different item does not reopen the achieved item.

The controller also hashes the exact `SPEC.json` bytes. It uses that full digest
with the base commit to stop an active run if desired state or source authority
changes. Each agent and gate heartbeat also checks the run generation and lease
time. An authority loss makes the run stale before candidate evaluation or
promotion can continue.

Before it synchronizes or dispatches work, the controller acquires a renewable
SQLite ownership lease for the resolved base repository. Each state mutation
checks the controller owner token and generation. A replacement controller can
acquire a higher generation only after graceful release or lease expiry.

Before an automatic fast-forward, SQLite stores an immutable promotion intent.
A replacement controller checks that intent before it creates a new claim. If
the base is the intended candidate and both SPEC identities are current, one
SQLite transaction repairs the run, item achievement, and self-improvement
decision. If the base is unchanged, the old run becomes stale and retryable.
If the base diverged or SPEC authority changed, recovery records refusal and
does not run a Git command. Recovery preserves the recorded worktree.

## Important limitations

- Controller ownership uses local SQLite transactions and wall-clock expiry. It
  is not a distributed consensus protocol.
- Promotion is local and fast-forward only.
- A configured agent can change files inside its worktree.
- Sandbox strength depends on the configured agent and operating system.
- The project does not yet provide remote scheduling, distributed leases,
  credential brokering, or automatic pull request creation.
- Self-improvement quality uses committed Git line and file counts. It does not
  measure performance, maintainability, or semantic value. Git does not provide
  line counts for binary changes, so a binary path contributes one changed file
  and zero changed lines.
- Root-level `pytest-of-*` temporary trees are ignored. The candidate commit
  guard rejects other generated nested repositories before evaluation.
- No license has been granted for this repository.

## Writing-standard boundary

Project instructions use controlled technical English where practical.
Automated checks can find some terminology and style problems. They do not
replace the complete ASD-STE100 Issue 9 procedure. Full compliance requires an
authorized standard, approved terminology, complete word and rule evidence,
and two qualified human reviewers for the exact revision.

Run the limited precheck with `autobuild writing-check`. Read
[`docs/writing-standard.md`](docs/writing-standard.md) for its exact boundary.

## Contributing and support

Read [`CONTRIBUTING.md`](CONTRIBUTING.md) before you submit a change. Use the
GitHub issue tracker for defects and security-neutral support questions. Use
the private reporting route in [`SECURITY.md`](SECURITY.md) for vulnerabilities.
