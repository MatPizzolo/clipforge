"""Checks on the docs that sessions share (card 001, action 3). Fast, no network."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from clipforge.config import Settings

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "docs" / "studio" / "10-decision-log.md"
DECISIONS = ROOT / "docs" / "DECISIONS.md"
PROPOSED = ROOT / "docs" / "studio" / "05-proposed-adrs.md"
CARDS = ROOT / "docs" / "cards"

_ROW = re.compile(r"^\|\s*(\d+)\s*\|", re.MULTILINE)
_ADR = re.compile(r"^## ADR-(\d+):", re.MULTILINE)
_LINK = re.compile(r"(?<!!)\[[^\]\n]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_FENCE = re.compile(r"^(```|~~~).*?^\1", re.MULTILINE | re.DOTALL)
_CODE = re.compile(r"`[^`\n]*`")

# 05 still carries full copies of the ADRs accepted in the 2026-09-29 kickoff review. They go
# when the owner of 05 trims them (card 001 report, open issue); a new copy fails this test, and
# so does a stale entry here once its copy is gone.
KNOWN_05_COPIES = {25, 26, 28, 29, 30, 31, 34, 35, 38, 39}


def log_numbers() -> list[int]:
    return [int(n) for n in _ROW.findall(LOG.read_text())]


def test_decision_log_numbers_are_unique() -> None:
    numbers = log_numbers()
    duplicates = sorted({n for n in numbers if numbers.count(n) > 1})
    assert duplicates == []


def test_superseded_rows_point_at_existing_rows() -> None:
    numbers = set(log_numbers())
    targets = re.findall(r"superseded(?: in part)? by (\d+)", LOG.read_text())
    assert targets, "the pattern stopped matching; check the log's status wording"
    assert sorted(int(t) for t in targets if int(t) not in numbers) == []


def adr_sections(path: Path) -> dict[int, str]:
    text = path.read_text()
    matches = list(_ADR.finditer(text))
    sections = {}
    for match, following in zip(matches, [*matches[1:], None], strict=True):
        end = following.start() if following else len(text)
        sections[int(match.group(1))] = text[match.start() : end]
    return sections


def test_adr_headings_are_unique_and_increasing() -> None:
    numbers = [int(n) for n in _ADR.findall(DECISIONS.read_text())]
    assert numbers == sorted(set(numbers))


def _decision_text(section: str) -> str:
    """The Context and Decision lines of an ADR, whitespace-normalized."""
    keep = [
        line
        for line in section.splitlines()
        if line.startswith(("Context:", "Decision:", "- ")) and len(line) > 40
    ]
    return " ".join(" ".join(keep).split())


def _accepted(section: str) -> bool:
    status = next((line for line in section.splitlines() if "Status:" in line), "")
    return "Accepted" in status


def test_proposed_adrs_dont_repeat_accepted_ones() -> None:
    accepted = {n: s for n, s in adr_sections(DECISIONS).items() if _accepted(s)}
    proposed = adr_sections(PROPOSED)
    copies = {
        n
        for n, section in proposed.items()
        if n in accepted
        and _decision_text(section)
        and _decision_text(section) == _decision_text(accepted[n])
    }
    assert copies - KNOWN_05_COPIES == set(), (
        "05 repeats an accepted ADR: keep it only in DECISIONS.md"
    )
    assert KNOWN_05_COPIES - copies == set(), (
        "these copies are gone: remove them from KNOWN_05_COPIES"
    )


def markdown_files() -> list[Path]:
    files = sorted((ROOT / "docs").rglob("*.md"))
    return files + [ROOT / name for name in ("README.md", "CLAUDE.md", "STATUS.md")]


def relative_links(path: Path) -> list[str]:
    text = _CODE.sub("", _FENCE.sub("", path.read_text()))
    links = []
    for target in _LINK.findall(text):
        if re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith("#"):
            continue  # http(s), mailto, in-page anchors
        links.append(target)
    return links


@pytest.mark.parametrize("path", markdown_files(), ids=lambda p: str(p.relative_to(ROOT)))
def test_relative_links_resolve(path: Path) -> None:
    broken = []
    for target in relative_links(path):
        file_part = target.split("#", 1)[0]
        if not file_part:
            continue
        resolved = (
            (ROOT / file_part.lstrip("/")) if file_part.startswith("/") else path.parent / file_part
        )
        if not resolved.exists():
            broken.append(target)
    assert broken == []


def test_link_pattern_finds_links() -> None:
    assert relative_links(ROOT / "docs" / "cards" / "README.md")


@pytest.mark.parametrize("card", sorted(CARDS.glob("[0-9][0-9][0-9]-*.md")), ids=lambda p: p.name)
def test_cards_have_a_status_and_a_log_range(card: Path) -> None:
    head = "\n".join(card.read_text().splitlines()[:12])
    assert re.search(r"^Status: \S", head, re.MULTILINE), "no Status line"
    assert re.search(r"^Decision-log range: #\d+\u2013#\d+", head, re.MULTILINE), "no log range"


# Settings without a default that .env.example may leave out, and why.
ENV_EXAMPLE_EXCEPTIONS: dict[str, str] = {}


def test_env_example_lists_every_required_setting() -> None:
    listed = set(
        re.findall(r"^([A-Z][A-Z0-9_]*)=", (ROOT / ".env.example").read_text(), re.MULTILINE)
    )
    required = {
        name.upper()
        for name, field in Settings.model_fields.items()
        if field.is_required() and name.upper() not in ENV_EXAMPLE_EXCEPTIONS
    }
    assert required - listed == set()
