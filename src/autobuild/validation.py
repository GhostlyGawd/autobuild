"""Static and live contract validation."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import load_config
from .spec import load_spec


@dataclass(frozen=True)
class ValidationFinding:
    check: str
    passed: bool
    detail: str


def validate_repository(root: Path, *, skip_git_clean: bool = False) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    try:
        config = load_config(root)
        findings.append(ValidationFinding("config", True, "configuration is valid"))
    except Exception as error:
        return [ValidationFinding("config", False, str(error))]

    try:
        specification = load_spec(root / "SPEC.json")
        findings.append(
            ValidationFinding(
                "spec",
                True,
                f"{len(specification.work_items)} work items; digest {specification.digest[:12]}",
            )
        )
    except Exception as error:
        findings.append(ValidationFinding("spec", False, str(error)))

    for executable in ("git", config.agent.command[0]):
        resolved = shutil.which(executable)
        findings.append(
            ValidationFinding(
                f"executable:{executable}",
                resolved is not None,
                f"available as {resolved}" if resolved else "not found on PATH",
            )
        )

    if not skip_git_clean:
        process = subprocess.run(
            ("git", "status", "--porcelain"),
            cwd=root,
            capture_output=True,
            text=True,
            shell=False,
            check=False,
        )
        findings.append(
            ValidationFinding(
                "git-clean",
                process.returncode == 0 and not process.stdout.strip(),
                "clean" if not process.stdout.strip() else "uncommitted changes present",
            )
        )

    contract_path = root / "docs" / "reconciled-agent-loop.json"
    schema_path = root / "docs" / "schemas" / "reconciled-agent-loop.schema.json"
    if importlib.util.find_spec("jsonschema") is None:
        findings.append(
            ValidationFinding(
                "lifecycle-contract",
                False,
                "jsonschema is not installed; install the dev dependencies",
            )
        )
    else:
        import jsonschema

        try:
            jsonschema.Draft202012Validator.check_schema(
                json.loads(schema_path.read_text(encoding="utf-8"))
            )
            jsonschema.validate(
                json.loads(contract_path.read_text(encoding="utf-8")),
                json.loads(schema_path.read_text(encoding="utf-8")),
            )
            findings.append(
                ValidationFinding(
                    "lifecycle-contract", True, "Draft 2020-12 schema validation passed"
                )
            )
        except Exception as error:
            findings.append(ValidationFinding("lifecycle-contract", False, str(error)))
    return findings
