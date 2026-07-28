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
[[gates]]
name = "test"
command = ["python", "-V"]
timeout_seconds = 10
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="state_path must stay inside"):
        load_config(tmp_path)

