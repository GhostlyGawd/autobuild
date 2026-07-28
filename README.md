# autobuild

`autobuild` is a local-first harness for autonomous engineering. It converts a
version-controlled specification into fenced, resumable work. It runs an agent
in an isolated Git worktree, evaluates the result, and promotes only a verified
commit.

Status: early development. The control loop and safety contracts are usable,
but the project is not production-ready.

## What it does

- Keeps desired outcomes in `SPEC.json`.
- Keeps execution state and evidence in SQLite.
- Reconciles desired state instead of trusting a worker process.
- Uses lease generations to reject stale worker events.
- Runs agents in isolated Git worktrees.
- runs verification gates without a command shell.
- Revalidates the SPEC and base commit before dispatch and promotion.
- Uses the same path for product work and bounded self-improvement.
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

Run one reconciliation cycle:

```text
autobuild run --once
```

The default configuration uses `codex exec` with workspace-write sandboxing.
Review `.autobuild/config.toml` before the first live run. A successful agent
process is not sufficient for promotion. All configured gates must pass.

## Project contract

- [`SPEC.json`](SPEC.json) defines the desired outcomes and acceptance checks.
- [`docs/WORKPAD.md`](docs/WORKPAD.md) records the current build state and
  validation evidence.
- [`docs/reconciled-agent-loop.json`](docs/reconciled-agent-loop.json) defines
  lifecycle ownership, recovery, and cleanup.
- [`docs/architecture.md`](docs/architecture.md) explains the system flow and
  current limitations.
- [`SECURITY.md`](SECURITY.md) defines the trust and containment boundaries.

## Important limitations

- The harness currently supports one local controller for each state database.
- Promotion is local and fast-forward only.
- A configured agent can change files inside its worktree.
- Sandbox strength depends on the configured agent and operating system.
- The project does not yet provide remote scheduling, distributed leases,
  credential brokering, or automatic pull request creation.
- No license has been granted for this repository.

## Writing-standard boundary

Project instructions use controlled technical English where practical.
Automated checks can find some terminology and style problems. They do not
replace the complete ASD-STE100 Issue 9 procedure. Full compliance requires an
authorized standard, approved terminology, complete word and rule evidence,
and two qualified human reviewers for the exact revision.

## Contributing and support

Read [`CONTRIBUTING.md`](CONTRIBUTING.md) before you submit a change. Use the
GitHub issue tracker for defects and security-neutral support questions. Use
the private reporting route in [`SECURITY.md`](SECURITY.md) for vulnerabilities.
