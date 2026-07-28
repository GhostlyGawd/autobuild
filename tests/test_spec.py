from __future__ import annotations

import json
from pathlib import Path

import pytest

from autobuild.models import WorkKind
from autobuild.spec import SpecError, load_spec


def test_load_spec_returns_typed_items(tmp_path: Path) -> None:
    path = tmp_path / "SPEC.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "objective": "Build a harness.",
                "work_items": [
                    {
                        "id": "one",
                        "kind": "self-improvement",
                        "priority": 7,
                        "objective": "Improve the harness.",
                        "acceptance": ["All gates pass."],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    specification = load_spec(path)

    assert specification.objective == "Build a harness."
    assert specification.work_items[0].kind is WorkKind.SELF_IMPROVEMENT
    assert specification.work_items[0].spec_digest == specification.digest


def test_load_spec_rejects_duplicate_ids(tmp_path: Path) -> None:
    path = tmp_path / "SPEC.json"
    item = {
        "id": "duplicate",
        "kind": "product",
        "priority": 1,
        "objective": "Do work.",
        "acceptance": ["It works."],
    }
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "objective": "Build.",
                "work_items": [item, item],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(SpecError, match="duplicate work item id"):
        load_spec(path)

