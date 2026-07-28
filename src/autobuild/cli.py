"""Command-line interface."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from .config import load_config
from .models import WorkKind
from .orchestrator import Orchestrator
from .spec import load_spec
from .state import StateStore
from .validation import validate_repository
from .writing import PRECHECK_NOTICE, RELEASE_STATUS, check_configured_documents


def _root(value: str) -> Path:
    return Path(value).resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="autobuild")
    parser.add_argument("--root", default=".", type=_root, help="repository root")
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate", help="validate the repository contract")
    validate.add_argument("--skip-git-clean", action="store_true")

    status = commands.add_parser("status", help="show desired and execution state")
    status.add_argument("--json", action="store_true", dest="as_json")

    run = commands.add_parser("run", help="run the reconciliation loop")
    run.add_argument("--once", action="store_true", required=True)
    run.add_argument(
        "--kind",
        choices=[kind.value for kind in WorkKind],
        help="limit selection to one work kind",
    )
    commands.add_parser(
        "writing-check",
        help="run the limited controlled-English precheck",
    )
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(arguments)
    root: Path = args.root

    if args.command == "validate":
        findings = validate_repository(root, skip_git_clean=args.skip_git_clean)
        for finding in findings:
            marker = "PASS" if finding.passed else "FAIL"
            print(f"{marker} {finding.check}: {finding.detail}")
        return 0 if all(finding.passed for finding in findings) else 1

    if args.command == "writing-check":
        print(PRECHECK_NOTICE)
        findings = check_configured_documents(root)
        for finding in findings:
            relative = finding.path.relative_to(root)
            print(
                f"FAIL {relative}:{finding.line} "
                f"{finding.check}: {finding.message}"
            )
        if not findings:
            print("NO AUTOMATED FINDINGS")
        print(RELEASE_STATUS)
        return 0 if not findings else 1

    config = load_config(root)
    store = StateStore(config.state_path)
    specification = load_spec(root / "SPEC.json")

    if args.command == "status":
        state = store.status()
        stored_items = {
            str(item["id"]): item for item in state["work_items"]
        }
        work_items = []
        for item in sorted(
            specification.work_items,
            key=lambda candidate: (-candidate.priority, candidate.id),
        ):
            work_items.append(
                stored_items.pop(
                    item.id,
                    {
                        "id": item.id,
                        "kind": item.kind.value,
                        "priority": item.priority,
                        "status": "ready",
                        "attempt_count": 0,
                        "updated_at": None,
                    },
                )
            )
        work_items.extend(
            stored_items[item_id] for item_id in sorted(stored_items)
        )
        payload = {
            "objective": specification.objective,
            "spec_digest": specification.digest,
            **state,
            "work_items": work_items,
        }
        if args.as_json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"Objective: {payload['objective']}")
            print(f"SPEC: {specification.digest[:12]}")
            for item in payload["work_items"]:
                print(
                    f"- {item['id']}: {item['status']} "
                    f"(attempts={item['attempt_count']}, priority={item['priority']})"
                )
        return 0

    if args.command == "run":
        kind = WorkKind(args.kind) if args.kind else None
        outcome = Orchestrator(root, config).reconcile_once(kind=kind)
        print(f"{outcome.status}: {outcome.detail}")
        if outcome.worktree:
            print(f"Preserved worktree: {outcome.worktree}")
        return 0 if outcome.status in {"idle", "succeeded", "awaiting-promotion"} else 1

    parser.error("unknown command")
    return 2
