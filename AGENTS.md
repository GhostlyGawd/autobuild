# Repository instructions

## Product outcome

Build `autobuild` as a local-first autonomous engineering harness. The harness
must converge from version-controlled desired state to verified Git state. It
must preserve evidence and recover after worker or controller failure.

## Authority

- `SPEC.json` owns desired product outcomes.
- Git owns source state.
- `.autobuild/state.db` owns execution history, leases, and event evidence.
- A worker process is never authoritative.
- `docs/WORKPAD.md` is the one durable project workpad.

## Required engineering behavior

- Revalidate the SPEC revision and base Git commit before dispatch and
  promotion.
- Fence mutable run events with a lease generation.
- Use argument arrays. Do not use a command shell for configured gates.
- Keep failed or uncertain worktrees until the state database records a
  semantic disposition.
- Add lifecycle tests for changed state transitions and failure boundaries.
- Update specifications, tests, user documentation, architecture, security
  boundaries, and the workpad in the same change when behavior changes.
- Do not add a full-compliance ASD-STE100 claim from automated checks. Full
  compliance requires the complete authorized workflow and two qualified human
  reviewers for the exact revision.

## Change quality

Run these commands before promotion:

```text
python -m pytest
python -m ruff check .
python -m autobuild writing-check
python -m autobuild validate
```

Do not put secrets, access tokens, personal paths, private prompts, or raw agent
transcripts in committed evidence.
