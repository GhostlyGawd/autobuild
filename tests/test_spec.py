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
    assert len(specification.work_items[0].spec_digest) == 64
    assert specification.work_items[0].spec_digest != specification.digest


def test_item_digest_ignores_unrelated_specification_changes(tmp_path: Path) -> None:
    path = tmp_path / "SPEC.json"
    item = {
        "id": "one",
        "kind": "product",
        "priority": 1,
        "objective": "Complete one.",
        "acceptance": ["One is complete."],
    }
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "objective": "Build.",
                "work_items": [item],
            }
        ),
        encoding="utf-8",
    )
    initial = load_spec(path)

    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "objective": "Build more.",
                "work_items": [
                    {
                        "acceptance": ["One is complete."],
                        "objective": "Complete one.",
                        "priority": 1,
                        "kind": "product",
                        "id": "one",
                    },
                    {
                        "id": "two",
                        "kind": "product",
                        "priority": 2,
                        "objective": "Complete two.",
                        "acceptance": ["Two is complete."],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    expanded = load_spec(path)

    assert expanded.digest != initial.digest
    assert expanded.work_items[0].spec_digest == initial.work_items[0].spec_digest

    item["acceptance"] = ["One is demonstrably complete."]
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "objective": "Build.",
                "work_items": [item],
            }
        ),
        encoding="utf-8",
    )

    assert load_spec(path).work_items[0].spec_digest != initial.work_items[0].spec_digest


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
