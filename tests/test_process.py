from __future__ import annotations

import os
import sys
from pathlib import Path

from autobuild.models import Gate
from autobuild.process import redact_text, run_gate, safe_environment


def test_safe_environment_excludes_unapproved_secret(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AUTOBUILD_TEST_SECRET", "do-not-inherit")
    monkeypatch.setenv("AUTOBUILD_TEST_ALLOWED", "inherit")

    environment = safe_environment(frozenset({"AUTOBUILD_TEST_ALLOWED"}))

    assert environment == {"AUTOBUILD_TEST_ALLOWED": "inherit"}
    assert "AUTOBUILD_TEST_SECRET" not in environment


def test_safe_environment_rejects_secret_name_even_if_allowed(monkeypatch) -> None:
    monkeypatch.setenv("AUTOBUILD_TEST_TOKEN", "do-not-inherit")

    environment = safe_environment(
        frozenset({"AUTOBUILD_TEST_TOKEN"}),
        ("TOKEN",),
    )

    assert environment == {}


def test_redact_text_removes_environment_and_known_token_shapes(monkeypatch) -> None:
    monkeypatch.setenv("AUTOBUILD_TEST_SECRET", "environment-secret")
    text = (
        "environment-secret "
        "ghp_abcdefghijklmnopqrstuvwxyz123456 "
        "Bearer abc.def-123"
    )

    redacted = redact_text(text, ("SECRET",))

    assert "environment-secret" not in redacted
    assert "ghp_" not in redacted
    assert "abc.def-123" not in redacted
    assert redacted.count("[REDACTED]") == 3


def test_gate_arguments_do_not_invoke_a_shell(tmp_path: Path) -> None:
    marker = tmp_path / "must-not-exist"
    gate = Gate(
        name="literal-argument",
        command=(
            sys.executable,
            "-c",
            "import sys; raise SystemExit(0 if sys.argv[1].startswith(';') else 1)",
            f"; echo unsafe > {marker}",
        ),
        timeout_seconds=10,
    )

    result = run_gate(gate, tmp_path, os.environ)

    assert result.passed
    assert not marker.exists()
