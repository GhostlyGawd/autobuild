from __future__ import annotations

from pathlib import Path

import pytest

from autobuild.config import ConfigError, load_config


def test_config_rejects_state_path_escape(tmp_path: Path) -> None:
    config_dir = tmp_path / ".autobuild"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        """
schema_version = 1
state_path = "../outside.db"
worktree_root = ".autobuild/worktrees"
result_root = ".autobuild/results"
lease_seconds = 10
max_attempts = 1
auto_promote = true
[agent]
kind = "fake"
command = ["python"]
timeout_seconds = 10
[policy]
allowed_environment = ["PATH"]
redacted_name_fragments = ["TOKEN"]
[self_improvement]
max_candidates = 2
candidate_timeout_seconds = 20
[[gates]]
name = "test"
command = ["python", "-V"]
timeout_seconds = 10
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="state_path must stay inside"):
        load_config(tmp_path)


def test_config_requires_bounded_self_improvement_policy(tmp_path: Path) -> None:
    config_dir = tmp_path / ".autobuild"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        """
schema_version = 1
state_path = ".autobuild/state.db"
worktree_root = ".autobuild/worktrees"
result_root = ".autobuild/results"
lease_seconds = 10
max_attempts = 1
auto_promote = true
[agent]
kind = "fake"
command = ["python"]
timeout_seconds = 10
[policy]
allowed_environment = ["PATH"]
redacted_name_fragments = ["TOKEN"]
[self_improvement]
max_candidates = 0
candidate_timeout_seconds = 20
[[gates]]
name = "test"
command = ["python", "-V"]
timeout_seconds = 10
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(
        ConfigError,
        match="max_candidates must be an integer greater than or equal to 1",
    ):
        load_config(tmp_path)

    invalid_duration = (config_dir / "config.toml").read_text(
        encoding="utf-8"
    ).replace("max_candidates = 0", "max_candidates = 2").replace(
        "candidate_timeout_seconds = 20",
        "candidate_timeout_seconds = 0",
    )
    (config_dir / "config.toml").write_text(
        invalid_duration,
        encoding="utf-8",
    )
    with pytest.raises(
        ConfigError,
        match=(
            "candidate_timeout_seconds must be an integer greater than "
            "or equal to 1"
        ),
    ):
        load_config(tmp_path)


def test_config_rejects_duplicate_gate_names(tmp_path: Path) -> None:
    config_dir = tmp_path / ".autobuild"
    config_dir.mkdir()
    config = """
schema_version = 1
state_path = ".autobuild/state.db"
worktree_root = ".autobuild/worktrees"
result_root = ".autobuild/results"
lease_seconds = 10
max_attempts = 1
auto_promote = true
[agent]
kind = "fake"
command = ["python"]
timeout_seconds = 10
[policy]
allowed_environment = ["PATH"]
redacted_name_fragments = ["TOKEN"]
[self_improvement]
max_candidates = 2
candidate_timeout_seconds = 20
[[gates]]
name = "test"
command = ["python", "-V"]
timeout_seconds = 10
[[gates]]
name = "test"
command = ["python", "-V"]
timeout_seconds = 10
""".strip()
    (config_dir / "config.toml").write_text(config, encoding="utf-8")

    with pytest.raises(ConfigError, match="gate names must be unique"):
        load_config(tmp_path)

