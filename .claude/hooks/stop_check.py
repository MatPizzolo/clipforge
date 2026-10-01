#!/usr/bin/env python3
"""Stop check (card 001, action 9; decision log #130): if files changed since the last green
`scripts/check.sh`, block the stop once and ask for the check and the report.

scripts/check.sh writes .superpowers/check-ok (the working tree's hash, from
scripts/tree_hash.sh) after a green full run. Nothing changed against HEAD, or a tree equal to
the marker, lets the session stop. `stop_hook_active` (a stop already blocked once) always lets
it stop, so this never loops. Any error lets it stop.

On `main` and `coord/` branches (the coordinator, who has no card report) it asks only for the
green check, not for a report (card 008).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

MARKER = Path(".superpowers") / "check-ok"
CHECK = "Files changed since the last green scripts/check.sh. Run scripts/check.sh until it's green"
REPORT = " and write or update your report in docs/reports/ (docs/templates/handoff-report.md)"
MID_TASK = ". If you're mid-task and not at a checkpoint, say so in one line and stop."
COORDINATOR_PREFIX = "coord/"


def reason(branch: str) -> str:
    """The coordinator (on `main` or `coord/`) has no card report to write."""
    if branch == "main" or branch.startswith(COORDINATOR_PREFIX):
        return CHECK + MID_TASK
    return CHECK + REPORT + MID_TASK


def should_block(root: Path, stop_hook_active: bool) -> bool:
    if stop_hook_active:
        return False
    tree = subprocess.run(
        [str(root / "scripts" / "tree_hash.sh")], cwd=root, capture_output=True, text=True
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=root, capture_output=True, text=True
    )
    if tree.returncode != 0 or head.returncode != 0:
        return False
    current = tree.stdout.strip()
    if current == head.stdout.strip():
        return False  # nothing changed
    marker = root / MARKER
    return not (marker.is_file() and marker.read_text().strip() == current)


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
        if not (root / "scripts" / "tree_hash.sh").is_file():
            return 0
        block = should_block(root, bool(event.get("stop_hook_active")))
        if block:
            branch = subprocess.run(
                ["git", "branch", "--show-current"], cwd=root, capture_output=True, text=True
            ).stdout.strip()
    except Exception:
        return 0
    if block:
        print(json.dumps({"decision": "block", "reason": reason(branch)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
