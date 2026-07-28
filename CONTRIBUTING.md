# Contributing

`autobuild` is in early development. Open an issue before a large change so that
the change can be tied to a current SPEC outcome.

## Local checks

```text
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check .
python -m autobuild validate
```

Add a lifecycle test when a change affects state, retries, leases, dispatch,
promotion, preservation, or cleanup. Update `SPEC.json`, `docs/WORKPAD.md`, and
the affected product documentation in the same change.

Do not submit secrets, private prompts, personal file paths, raw agent
transcripts, or generated evidence that cannot be reproduced.

By submitting a contribution, you confirm that you have the right to submit it.
This repository does not currently grant a license to use or redistribute its
contents.

