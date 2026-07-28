"""Contained process execution for agents and gates."""

from __future__ import annotations

import os
import re
import subprocess
import time
from collections.abc import Mapping
from pathlib import Path

from .models import Gate, GateResult

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


def run_gate(gate: Gate, cwd: Path, environment: Mapping[str, str]) -> GateResult:
    started = time.monotonic()
    try:
        process = subprocess.run(
            gate.command,
            cwd=cwd,
            env=dict(environment),
            capture_output=True,
            text=True,
            timeout=gate.timeout_seconds,
            shell=False,
            check=False,
        )
        return GateResult(
            name=gate.name,
            command=gate.command,
            returncode=process.returncode,
            duration_seconds=time.monotonic() - started,
            stdout=process.stdout[-_OUTPUT_LIMIT:],
            stderr=process.stderr[-_OUTPUT_LIMIT:],
        )
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout.decode() if isinstance(error.stdout, bytes) else (error.stdout or "")
        stderr = error.stderr.decode() if isinstance(error.stderr, bytes) else (error.stderr or "")
        return GateResult(
            name=gate.name,
            command=gate.command,
            returncode=None,
            duration_seconds=time.monotonic() - started,
            stdout=stdout[-_OUTPUT_LIMIT:],
            stderr=stderr[-_OUTPUT_LIMIT:],
            timed_out=True,
        )
