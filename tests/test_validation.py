from __future__ import annotations

import json
from pathlib import Path

import jsonschema


def test_reconciled_loop_contract_matches_schema() -> None:
    root = Path(__file__).parents[1]
    schema = json.loads(
        (root / "docs" / "schemas" / "reconciled-agent-loop.schema.json").read_text(
            encoding="utf-8"
        )
    )
    contract = json.loads(
        (root / "docs" / "reconciled-agent-loop.json").read_text(encoding="utf-8")
    )

    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(contract, schema)

