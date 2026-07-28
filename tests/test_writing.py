from __future__ import annotations

from pathlib import Path

from autobuild.writing import (
    PRECHECK_NOTICE,
    RELEASE_STATUS,
    check_markdown,
)


def test_precheck_reports_long_descriptive_sentence(tmp_path: Path) -> None:
    path = tmp_path / "document.md"
    path.write_text(
        "One two three four five six seven eight nine ten eleven twelve thirteen "
        "fourteen fifteen sixteen seventeen eighteen nineteen twenty twenty-one "
        "twenty-two twenty-three twenty-four twenty-five twenty-six.\n",
        encoding="utf-8",
    )

    findings = check_markdown(path, "descriptive", maximum_words=25)

    assert len(findings) == 1
    assert findings[0].check == "approximate-sentence-word-count"


def test_precheck_ignores_fenced_code(tmp_path: Path) -> None:
    path = tmp_path / "document.md"
    path.write_text(
        "Short text.\n\n```\n"
        "one two three four five six seven eight nine ten eleven twelve\n"
        "```\n",
        encoding="utf-8",
    )

    findings = check_markdown(path, "procedural", maximum_words=5)

    assert findings == []


def test_precheck_labels_do_not_claim_compliance() -> None:
    assert "NOT AN ASD-STE100 COMPLIANCE CHECK" in PRECHECK_NOTICE
    assert RELEASE_STATUS == "NOT RELEASED — COMPLIANCE CHECK INCOMPLETE"

