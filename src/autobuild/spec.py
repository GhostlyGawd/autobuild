"""Version-controlled desired-state specification."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import WorkItem, WorkKind


class SpecError(ValueError):
    """The desired-state specification is invalid."""


@dataclass(frozen=True)
class Specification:
    objective: str
    digest: str
    work_items: tuple[WorkItem, ...]


def _nonempty_text(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SpecError(f"{location} must be a nonempty string")
    return value.strip()


def load_spec(path: Path) -> Specification:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as error:
        raise SpecError(f"SPEC.json is not valid JSON: {error}") from error
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise SpecError("SPEC.json schema_version must be 1")

    objective = _nonempty_text(data.get("objective"), "objective")
    raw_items = data.get("work_items")
    if not isinstance(raw_items, list) or not raw_items:
        raise SpecError("work_items must be a nonempty list")

    seen: set[str] = set()
    items: list[WorkItem] = []
    for index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, dict):
            raise SpecError(f"work_items[{index}] must be an object")
        item_digest = hashlib.sha256(
            json.dumps(
                raw_item,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        item_id = _nonempty_text(raw_item.get("id"), f"work_items[{index}].id")
        if item_id in seen:
            raise SpecError(f"duplicate work item id: {item_id}")
        seen.add(item_id)
        try:
            kind = WorkKind(raw_item.get("kind"))
        except ValueError as error:
            raise SpecError(f"work_items[{index}].kind is invalid") from error
        priority = raw_item.get("priority")
        if not isinstance(priority, int) or isinstance(priority, bool):
            raise SpecError(f"work_items[{index}].priority must be an integer")
        acceptance = raw_item.get("acceptance")
        if not isinstance(acceptance, list) or not acceptance:
            raise SpecError(f"work_items[{index}].acceptance must be a nonempty list")
        items.append(
            WorkItem(
                id=item_id,
                kind=kind,
                priority=priority,
                objective=_nonempty_text(
                    raw_item.get("objective"), f"work_items[{index}].objective"
                ),
                acceptance=tuple(
                    _nonempty_text(value, f"work_items[{index}].acceptance")
                    for value in acceptance
                ),
                spec_digest=item_digest,
            )
        )
    return Specification(objective=objective, digest=digest, work_items=tuple(items))
