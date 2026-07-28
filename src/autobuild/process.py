"""Contained process execution for agents and gates."""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Mapping
from pathlib import Path

from .models import Gate, GateResult

_OUTPUT_LIMIT = 64_000


def safe_environment(allowed_names: frozenset[str]) -> dict[str, str]:
    return {name: value for name, value in os.environ.items() if name in allowed_names}


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
