# Security policy

## Trust model

`autobuild` treats the specification, base Git repository, and local policy as
trusted inputs. It treats agent output and worktree content as untrusted.

The controller applies these boundaries:

- It runs configured commands with argument arrays and `shell=False`.
- It gives child processes an allowlisted environment.
- It isolates agent edits in a Git worktree.
- It revalidates the SPEC digest and base commit before dispatch and promotion.
- It rejects events that have an expired or stale lease generation.
- It uses fast-forward-only promotion.
- It preserves failed worktrees for inspection.

These controls do not create a complete security sandbox. The configured agent,
operating system, Git hooks, test commands, package managers, and build tools can
execute code. Use an operating-system sandbox or disposable machine for
untrusted repositories.

## Secrets and privacy

Do not put secrets in `SPEC.json`, `.autobuild/config.toml`, prompts, committed
evidence, or test fixtures. The default child environment uses an allowlist, but
a repository process can still access files allowed by the operating system.
Use scoped credentials and an external secret broker when credentials are
necessary. Credential brokering is not implemented yet.

## Reporting a vulnerability

Do not open a public issue for a vulnerability. Use GitHub private vulnerability
reporting when it is available for this repository. If that route is not
available, contact the repository owner through a private channel.

Include the affected commit, impact, reproduction steps, and suggested
containment. Do not include working credentials or private data.

