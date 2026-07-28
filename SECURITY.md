# Security policy

## Trust model

`autobuild` treats the specification, base Git repository, and local policy as
trusted inputs. It treats agent output and worktree content as untrusted.

The controller applies these boundaries:

- It runs configured commands with argument arrays and `shell=False`.
- It gives child processes an allowlisted environment.
- It denies allowlisted variables when their names match configured secret-name
  fragments.
- It redacts inherited secret values and common credential forms before it
  writes agent or gate output to durable events.
- It isolates agent edits in a Git worktree.
- It commits the candidate before verification and rejects later gate changes.
- It revalidates the SPEC digest and base commit before dispatch and promotion.
- It rejects events that have an expired or stale lease generation.
- It renews the lease during long agent and gate processes and stops the child
  process if renewal loses authority.
- It uses fast-forward-only promotion.
- It preserves failed worktrees for inspection.
- It records an agent-startup or controller exception as a terminal failed run
  when the current lease still has authority.

These controls do not create a complete security sandbox. The configured agent,
operating system, Git hooks, test commands, package managers, and build tools can
execute code. Use an operating-system sandbox or disposable machine for
untrusted repositories.

Output redaction is a defense-in-depth control. It cannot identify every secret
format or sensitive value. A process must not print secrets.

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
