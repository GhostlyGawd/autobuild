"""Configuration loading and validation."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import Gate

_MAX_SELF_IMPROVEMENT_CANDIDATES = 8
_MAX_SELF_IMPROVEMENT_CANDIDATE_SECONDS = 7_200
_MAX_SELF_IMPROVEMENT_TOTAL_SECONDS = 14_400


class ConfigError(ValueError):
    """The configuration is invalid."""


@dataclass(frozen=True)
class AgentConfig:
    kind: str
    command: tuple[str, ...]
    timeout_seconds: int


@dataclass(frozen=True)
class PolicyConfig:
    allowed_environment: frozenset[str]
    redacted_name_fragments: tuple[str, ...]


@dataclass(frozen=True)
class SelfImprovementConfig:
    max_candidates: int
    candidate_timeout_seconds: int


@dataclass(frozen=True)
class Config:
    root: Path
    state_path: Path
    worktree_root: Path
    result_root: Path
    lease_seconds: int
    max_attempts: int
    auto_promote: bool
    cleanup_succeeded_worktrees: bool
    agent: AgentConfig
    policy: PolicyConfig
    self_improvement: SelfImprovementConfig
    gates: tuple[Gate, ...]


def _require_int(
    data: dict[str, Any],
    name: str,
    *,
    minimum: int = 1,
    maximum: int | None = None,
) -> int:
    value = data.get(name)
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ConfigError(f"{name} must be an integer greater than or equal to {minimum}")
    if maximum is not None and value > maximum:
        raise ConfigError(f"{name} must be an integer less than or equal to {maximum}")
    return value


def _require_string_list(data: dict[str, Any], name: str) -> tuple[str, ...]:
    value = data.get(name)
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item for item in value)
    ):
        raise ConfigError(f"{name} must be a nonempty list of nonempty strings")
    return tuple(value)


def _inside(root: Path, value: str, name: str) -> Path:
    path = (root / value).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as error:
        raise ConfigError(f"{name} must stay inside the repository") from error
    return path


def load_config(root: Path, path: Path | None = None) -> Config:
    root = root.resolve()
    config_path = path or root / ".autobuild" / "config.toml"
    with config_path.open("rb") as stream:
        data = tomllib.load(stream)

    if data.get("schema_version") != 1:
        raise ConfigError("schema_version must be 1")

    agent_data = data.get("agent")
    policy_data = data.get("policy")
    self_improvement_data = data.get("self_improvement")
    gate_data = data.get("gates")
    if (
        not isinstance(agent_data, dict)
        or not isinstance(policy_data, dict)
        or not isinstance(self_improvement_data, dict)
    ):
        raise ConfigError("agent, policy, and self_improvement tables are required")
    if not isinstance(gate_data, list) or not gate_data:
        raise ConfigError("at least one gate is required")

    gates = []
    for index, item in enumerate(gate_data):
        if not isinstance(item, dict):
            raise ConfigError(f"gates[{index}] must be a table")
        name = item.get("name")
        if not isinstance(name, str) or not name:
            raise ConfigError(f"gates[{index}].name must be a nonempty string")
        gates.append(
            Gate(
                name=name,
                command=_require_string_list(item, "command"),
                timeout_seconds=_require_int(item, "timeout_seconds"),
            )
        )
    if len({gate.name for gate in gates}) != len(gates):
        raise ConfigError("gate names must be unique")
    max_candidates = _require_int(
        self_improvement_data,
        "max_candidates",
        maximum=_MAX_SELF_IMPROVEMENT_CANDIDATES,
    )
    candidate_timeout_seconds = _require_int(
        self_improvement_data,
        "candidate_timeout_seconds",
        maximum=_MAX_SELF_IMPROVEMENT_CANDIDATE_SECONDS,
    )
    if (
        max_candidates * candidate_timeout_seconds
        > _MAX_SELF_IMPROVEMENT_TOTAL_SECONDS
    ):
        raise ConfigError(
            "self-improvement candidate count times timeout must be less than "
            f"or equal to {_MAX_SELF_IMPROVEMENT_TOTAL_SECONDS} seconds"
        )

    return Config(
        root=root,
        state_path=_inside(root, str(data.get("state_path", "")), "state_path"),
        worktree_root=_inside(root, str(data.get("worktree_root", "")), "worktree_root"),
        result_root=_inside(root, str(data.get("result_root", "")), "result_root"),
        lease_seconds=_require_int(data, "lease_seconds"),
        max_attempts=_require_int(data, "max_attempts"),
        auto_promote=bool(data.get("auto_promote", False)),
        cleanup_succeeded_worktrees=bool(
            data.get("cleanup_succeeded_worktrees", False)
        ),
        agent=AgentConfig(
            kind=str(agent_data.get("kind", "")),
            command=_require_string_list(agent_data, "command"),
            timeout_seconds=_require_int(agent_data, "timeout_seconds"),
        ),
        policy=PolicyConfig(
            allowed_environment=frozenset(_require_string_list(policy_data, "allowed_environment")),
            redacted_name_fragments=_require_string_list(
                policy_data, "redacted_name_fragments"
            ),
        ),
        self_improvement=SelfImprovementConfig(
            max_candidates=max_candidates,
            candidate_timeout_seconds=candidate_timeout_seconds,
        ),
        gates=tuple(gates),
    )
