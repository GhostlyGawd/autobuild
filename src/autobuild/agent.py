"""Agent protocol and Codex CLI implementation."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from .config import AgentConfig
from .models import AgentResult, WorkItem
from .process import run_process

_OUTPUT_LIMIT = 64_000


def build_prompt(item: WorkItem, base_commit: str) -> str:
    checks = "\n".join(f"- {criterion}" for criterion in item.acceptance)
    return f"""\
You are the bounded implementation worker for autobuild.

Work item: {item.id}
Kind: {item.kind.value}
Base commit: {base_commit}

Objective:
{item.objective}

Acceptance criteria:
{checks}

Read AGENTS.md, SPEC.json, docs/WORKPAD.md, and the relevant source and tests.
Make only changes that are necessary for this work item. Do not change
repository settings, credentials, visibility, licensing, releases, or external
systems. Run focused tests. Do not merge, push, or delete the worktree.
Finish with a concise summary of changes, validation, and unresolved risks.
"""


def run_agent(
    config: AgentConfig,
    item: WorkItem,
    base_commit: str,
    worktree: Path,
    result_file: Path,
    environment: Mapping[str, str],
    *,
    heartbeat=None,
    heartbeat_interval_seconds: float = 30.0,
) -> AgentResult:
    result_file.parent.mkdir(parents=True, exist_ok=True)
    command = (
        *config.command,
        "--cd",
        str(worktree),
        "--output-last-message",
        str(result_file),
        "-",
    )
    result = run_process(
        command,
        worktree,
        environment,
        config.timeout_seconds,
        input_text=build_prompt(item, base_commit),
        heartbeat=heartbeat,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
    )
    summary = result_file.read_text(encoding="utf-8") if result_file.exists() else ""
    return AgentResult(
        returncode=result.returncode,
        summary=summary[-_OUTPUT_LIMIT:],
        stdout=result.stdout[-_OUTPUT_LIMIT:],
        stderr=result.stderr[-_OUTPUT_LIMIT:],
        timed_out=result.timed_out,
    )
