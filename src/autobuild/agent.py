"""Agent protocol and Codex CLI implementation."""

from __future__ import annotations

import subprocess
from collections.abc import Mapping
from pathlib import Path

from .config import AgentConfig
from .models import AgentResult, WorkItem

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
    try:
        process = subprocess.run(
            command,
            cwd=worktree,
            env=dict(environment),
            input=build_prompt(item, base_commit),
            capture_output=True,
            text=True,
            timeout=config.timeout_seconds,
            shell=False,
            check=False,
        )
        summary = result_file.read_text(encoding="utf-8") if result_file.exists() else ""
        return AgentResult(
            returncode=process.returncode,
            summary=summary[-_OUTPUT_LIMIT:],
            stdout=process.stdout[-_OUTPUT_LIMIT:],
            stderr=process.stderr[-_OUTPUT_LIMIT:],
        )
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout.decode() if isinstance(error.stdout, bytes) else (error.stdout or "")
        stderr = error.stderr.decode() if isinstance(error.stderr, bytes) else (error.stderr or "")
        return AgentResult(
            returncode=None,
            summary="",
            stdout=stdout[-_OUTPUT_LIMIT:],
            stderr=stderr[-_OUTPUT_LIMIT:],
            timed_out=True,
        )
