#!/usr/bin/env python3
"""SessionStart context (startup, resume, compact): the branch, its card, STATUS.md's next cards
and the session rules (card 001, action 9; decision log #130). After a compaction this is what
brings the card back. It never fails the session: on any error it prints nothing.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

RULES = """Rules for this session (CLAUDE.md, Sessions):
- Work only from the card; stay inside its scope (scripts/scopes.toml enforces it).
- Never commit, push, tag, deploy or stop the Modal app: give the owner the exact command.
- Run scripts/check.sh until it's green before every checkpoint.
- Reports go in docs/reports/NNN-<stream>-<YYYY-MM-DD>.md (docs/templates/handoff-report.md).
- docs/studio/10-decision-log.md is append-only, only rows in your range; re-read it first."""


def _section(text: str, heading: str) -> str:
    """The body of `## heading` up to the next `## ` heading."""
    match = re.search(rf"^## {re.escape(heading)}\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    return match.group(1).strip() if match else ""


def find_card(root: Path, branch: str) -> Path | None:
    # Cards write it mid-line: "Stream: S1 · Branch: `s1/finish` · Worktree: `../clipForge-s1`"
    pattern = re.compile(rf"\bBranch: `{re.escape(branch)}`")
    for card in sorted((root / "docs" / "cards").glob("[0-9][0-9][0-9]-*.md")):
        header = "\n".join(card.read_text().splitlines()[:12])
        if pattern.search(header):
            return card
    return None


def card_summary(root: Path, card: Path) -> str:
    text = card.read_text()
    title = next((line[2:] for line in text.splitlines() if line.startswith("# ")), card.name)
    header = [
        line
        for line in text.splitlines()[:12]
        if line.startswith(("Status:", "Decision-log range:", "Cost cap:", "Depends on:"))
    ]
    parts = [
        f"Card: docs/cards/{card.name}: {title}",
        *header,
        "Scope:",
        _section(text, "Scope"),
        "Checkpoints:",
        _section(text, "Checkpoints"),
        f"Start with: Run card docs/cards/{card.name} (re-read it in full before working).",
    ]
    return "\n".join(part for part in parts if part)


def build_context(root: Path, branch: str, source: str) -> str:
    lines = [f"ClipForge session context ({source}). Branch: {branch or '(detached)'}."]
    if branch == "main":
        lines.append(
            "WARNING: this is main, the coordinator's checkout. Card work belongs in the card's "
            "worktree (scripts/worktree.sh <branch>); on main only coord/ paths may be edited."
        )
    else:
        card = find_card(root, branch)
        if card is None:
            lines.append(f"No card in docs/cards/ names branch `{branch}`.")
        else:
            lines.append(card_summary(root, card))
    status = root / "STATUS.md"
    if status.is_file():
        next_cards = _section(status.read_text(), "Next cards (in order)")
        if next_cards:
            lines += ["STATUS.md, next cards:", next_cards]
    lines.append(RULES)
    return "\n\n".join(lines)


def main() -> int:
    try:
        event = json.load(sys.stdin)
        start = os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or "."
        top = subprocess.run(
            ["git", "-C", start, "rev-parse", "--show-toplevel"], capture_output=True, text=True
        )
        if top.returncode != 0:
            return 0
        root = Path(top.stdout.strip())
        branch = subprocess.run(
            ["git", "-C", str(root), "branch", "--show-current"], capture_output=True, text=True
        ).stdout.strip()
        context = build_context(root, branch, event.get("source", "startup"))
    except Exception:
        return 0
    print(
        json.dumps(
            {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
