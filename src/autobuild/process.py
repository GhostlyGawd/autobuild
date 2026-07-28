"""Contained process execution for agents and gates."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from collections.abc import Callable, Mapping
from pathlib import Path

from .models import Gate, GateResult, ProcessResult

_OUTPUT_LIMIT = 64_000
_CREDENTIAL_PATTERN = re.compile(
    r"(?i)\b(?:gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,})\b"
)
_BEARER_PATTERN = re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._~+/-]+=*")


def safe_environment(
    allowed_names: frozenset[str],
    redacted_name_fragments: tuple[str, ...] = (),
) -> dict[str, str]:
    fragments = tuple(fragment.casefold() for fragment in redacted_name_fragments)
    return {
        name: value
        for name, value in os.environ.items()
        if name in allowed_names
        and not any(fragment in name.casefold() for fragment in fragments)
    }


def redact_text(text: str, redacted_name_fragments: tuple[str, ...]) -> str:
    redacted = text
    fragments = tuple(fragment.casefold() for fragment in redacted_name_fragments)
    for name, value in os.environ.items():
        if (
            value
            and len(value) >= 4
            and any(fragment in name.casefold() for fragment in fragments)
        ):
            redacted = redacted.replace(value, "[REDACTED]")
    redacted = _CREDENTIAL_PATTERN.sub("[REDACTED]", redacted)
    return _BEARER_PATTERN.sub(r"\1[REDACTED]", redacted)


def run_process(
    command: tuple[str, ...],
    cwd: Path,
    environment: Mapping[str, str],
    timeout_seconds: float,
    *,
    input_text: str | None = None,
    heartbeat: Callable[[], None] | None = None,
    heartbeat_interval_seconds: float = 30.0,
) -> ProcessResult:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if heartbeat_interval_seconds <= 0:
        raise ValueError("heartbeat_interval_seconds must be positive")
    started = time.monotonic()
    deadline = started + timeout_seconds
    executable = shutil.which(command[0], path=environment.get("PATH"))
    if executable is None:
        raise FileNotFoundError(f"executable not found: {command[0]}")
    resolved_command = (executable, *command[1:])
    process = subprocess.Popen(
        resolved_command,
        cwd=cwd,
        env=dict(environment),
        stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
    )
    pending_input = input_text
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            process.kill()
            stdout, stderr = process.communicate()
            return ProcessResult(
                returncode=None,
                duration_seconds=time.monotonic() - started,
                stdout=stdout[-_OUTPUT_LIMIT:],
                stderr=stderr[-_OUTPUT_LIMIT:],
                timed_out=True,
            )
        try:
            stdout, stderr = process.communicate(
                input=pending_input,
                timeout=min(remaining, heartbeat_interval_seconds),
            )
            return ProcessResult(
                returncode=process.returncode,
                duration_seconds=time.monotonic() - started,
                stdout=stdout[-_OUTPUT_LIMIT:],
                stderr=stderr[-_OUTPUT_LIMIT:],
            )
        except subprocess.TimeoutExpired:
            pending_input = None
            if heartbeat is not None:
                try:
                    heartbeat()
                except BaseException:
                    process.kill()
                    process.communicate()
                    raise


def run_gate(
    gate: Gate,
    cwd: Path,
    environment: Mapping[str, str],
    *,
    heartbeat: Callable[[], None] | None = None,
    heartbeat_interval_seconds: float = 30.0,
) -> GateResult:
    result = run_process(
        gate.command,
        cwd,
        environment,
        gate.timeout_seconds,
        heartbeat=heartbeat,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
    )
    return GateResult(
        name=gate.name,
        command=gate.command,
        returncode=result.returncode,
        duration_seconds=result.duration_seconds,
        stdout=result.stdout,
        stderr=result.stderr,
        timed_out=result.timed_out,
    )
