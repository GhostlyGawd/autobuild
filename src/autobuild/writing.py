"""Fail-closed automated precheck for controlled technical English."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ContentType = Literal["descriptive", "procedural"]

_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_INLINE_CODE = re.compile(r"`[^`]+`")
_HTML = re.compile(r"<[^>]+>")
_WORD = re.compile(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*")
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
_LIST_MARKER = re.compile(r"^\s*(?:[-+*]|\d+[.)])\s+")

PRECHECK_NOTICE = "AUTOMATED PRECHECK ONLY — NOT AN ASD-STE100 COMPLIANCE CHECK"
RELEASE_STATUS = "NOT RELEASED — COMPLIANCE CHECK INCOMPLETE"


class WritingConfigError(ValueError):
    """The writing-precheck configuration is invalid."""


@dataclass(frozen=True)
class DocumentPolicy:
    path: Path
    content_type: ContentType


@dataclass(frozen=True)
class WritingPolicy:
    descriptive_max_words: int
    procedural_max_words: int
    descriptive_max_sentences_per_paragraph: int
    documents: tuple[DocumentPolicy, ...]


@dataclass(frozen=True)
class WritingFinding:
    path: Path
    line: int
    check: str
    message: str


def _positive_integer(data: dict[str, object], name: str) -> int:
    value = data.get(name)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise WritingConfigError(f"{name} must be a positive integer")
    return value


def load_writing_policy(root: Path) -> WritingPolicy:
    path = root / ".autobuild" / "writing.toml"
    with path.open("rb") as stream:
        data = tomllib.load(stream)
    if data.get("schema_version") != 1:
        raise WritingConfigError("writing schema_version must be 1")
    raw_documents = data.get("documents")
    if not isinstance(raw_documents, list) or not raw_documents:
        raise WritingConfigError("writing documents must be a nonempty list")
    documents: list[DocumentPolicy] = []
    for index, raw in enumerate(raw_documents):
        if not isinstance(raw, dict):
            raise WritingConfigError(f"documents[{index}] must be a table")
        raw_path = raw.get("path")
        content_type = raw.get("content_type")
        if not isinstance(raw_path, str) or not raw_path:
            raise WritingConfigError(f"documents[{index}].path must be a nonempty string")
        if content_type not in {"descriptive", "procedural"}:
            raise WritingConfigError(
                f"documents[{index}].content_type must be descriptive or procedural"
            )
        document_path = (root / raw_path).resolve()
        try:
            document_path.relative_to(root.resolve())
        except ValueError as error:
            raise WritingConfigError(
                f"documents[{index}].path must stay inside the repository"
            ) from error
        documents.append(DocumentPolicy(document_path, content_type))
    return WritingPolicy(
        descriptive_max_words=_positive_integer(data, "descriptive_max_words"),
        procedural_max_words=_positive_integer(data, "procedural_max_words"),
        descriptive_max_sentences_per_paragraph=_positive_integer(
            data, "descriptive_max_sentences_per_paragraph"
        ),
        documents=tuple(documents),
    )


def _plain_text(markdown: str) -> str:
    text = _LINK.sub(r"\1", markdown)
    text = _INLINE_CODE.sub(" identifier ", text)
    text = _HTML.sub(" ", text)
    return text.replace("*", "").replace("_", " ")


def _prose_blocks(text: str) -> list[tuple[int, str]]:
    blocks: list[tuple[int, str]] = []
    current: list[str] = []
    start_line = 1
    in_fence = False

    def flush() -> None:
        nonlocal current
        if current:
            blocks.append((start_line, " ".join(current)))
            current = []

    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            flush()
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if (
            not stripped
            or stripped.startswith("#")
            or stripped.startswith("|")
            or stripped.startswith("<!--")
        ):
            flush()
            continue
        if _LIST_MARKER.match(line):
            flush()
            blocks.append((line_number, _LIST_MARKER.sub("", line).strip()))
            continue
        if not current:
            start_line = line_number
        current.append(stripped)
    flush()
    return blocks


def check_markdown(
    path: Path,
    content_type: ContentType,
    *,
    maximum_words: int,
    maximum_sentences_per_paragraph: int = 6,
) -> list[WritingFinding]:
    if not path.is_file():
        return [WritingFinding(path, 1, "document", "configured document does not exist")]
    findings: list[WritingFinding] = []
    for line, block in _prose_blocks(path.read_text(encoding="utf-8")):
        sentences = [
            sentence.strip()
            for sentence in _SENTENCE_BOUNDARY.split(_plain_text(block))
            if sentence.strip()
        ]
        if content_type == "descriptive" and len(sentences) > maximum_sentences_per_paragraph:
            findings.append(
                WritingFinding(
                    path,
                    line,
                    "paragraph-sentence-count",
                    (
                        f"paragraph has {len(sentences)} sentences; "
                        f"configured maximum is {maximum_sentences_per_paragraph}"
                    ),
                )
            )
        for sentence in sentences:
            word_count = len(_WORD.findall(sentence))
            if word_count > maximum_words:
                findings.append(
                    WritingFinding(
                        path,
                        line,
                        "approximate-sentence-word-count",
                        (
                            f"sentence has approximately {word_count} words; "
                            f"configured maximum is {maximum_words}"
                        ),
                    )
                )
    return findings


def check_configured_documents(root: Path) -> list[WritingFinding]:
    policy = load_writing_policy(root)
    findings: list[WritingFinding] = []
    for document in policy.documents:
        maximum_words = (
            policy.descriptive_max_words
            if document.content_type == "descriptive"
            else policy.procedural_max_words
        )
        findings.extend(
            check_markdown(
                document.path,
                document.content_type,
                maximum_words=maximum_words,
                maximum_sentences_per_paragraph=(
                    policy.descriptive_max_sentences_per_paragraph
                ),
            )
        )
    return findings

