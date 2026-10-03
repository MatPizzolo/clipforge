"""Whether a CI run needs the full gate, or only the docs tests (card 017, action 2).

ci.yml's `changes` job runs this; `check` then runs `scripts/check.sh --docs` alone when only
docs changed, and the full gate otherwise. No workflow-level `paths:` filters: a required check
skipped by a filter stays "pending" forever, so `check` always runs and always reports.

Docs-only means every changed path is under `docs/`, a Markdown file at any level (not under
`prompts/`: the released prompts are code), or `.gitignore`. Anything else is code, and so is
an unknown base (a new branch, a force push). Tests that read real docs belong in
tests/test_docs.py, the only tests the docs-only path runs.

    python3 scripts/ci_changes.py --base origin/main      # prints code=true|false
    python3 scripts/ci_changes.py --base <sha> --diff two-dot --output "$GITHUB_OUTPUT"
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# `docs/**` (cards included), `**/*.md` (STATUS.md, ROADMAP.md, web/README.md), `.gitignore`
DOCS_ONLY = re.compile(r"\A(?:docs/.*|(?:.*/)?[^/]*\.md|\.gitignore)\Z")
# Markdown that the code loads: the released prompts (CLAUDE.md rule 4) are code
CODE_MARKDOWN = ("prompts/",)
NO_BASE = ("", "0" * 40)
DIFFS = {"three-dot": "...", "two-dot": ".."}


def is_docs(path: str) -> bool:
    return DOCS_ONLY.match(path) is not None and not path.startswith(CODE_MARKDOWN)


def needs_code_checks(paths: Iterable[str]) -> bool:
    """True unless every path is docs. An empty diff is docs-only: nothing to test."""
    return not all(is_docs(path) for path in paths)


def changed_paths(
    repo: Path, base: str, head: str = "HEAD", diff: str = "three-dot"
) -> list[str] | None:
    """The paths changed between `base` and `head`, or None when `base` is unusable.

    three-dot: what `head` changed since it left `base` (a PR against its base branch).
    two-dot: every difference between the two trees (a push to main against its last green
    commit, as the deploy job diffs), so a non-linear history can't hide a change."""
    if base in NO_BASE:
        return None
    known = subprocess.run(
        ["git", "cat-file", "-e", f"{base}^{{commit}}"], cwd=repo, capture_output=True
    )
    if known.returncode != 0:
        return None
    result = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", f"{base}{DIFFS[diff]}{head}"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.splitlines()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Does this change need the code checks?")
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--base", default="", help="the ref or SHA to diff against")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--diff", choices=sorted(DIFFS), default="three-dot")
    parser.add_argument("--output", type=Path, help="append code=… here ($GITHUB_OUTPUT)")
    args = parser.parse_args(argv)

    paths = changed_paths(args.repo, args.base, args.head, args.diff)
    if paths is None:
        print(f"no usable base ({args.base or 'none'}): running the code checks", file=sys.stderr)
        code = True
    else:
        code = needs_code_checks(paths)
        others = [p for p in paths if not is_docs(p)]
        print(f"{len(paths)} changed paths, {len(others)} outside the docs", file=sys.stderr)
        for path in others[:20]:
            print(f"  {path}", file=sys.stderr)
    line = f"code={'true' if code else 'false'}"
    print(line)
    if args.output is not None:
        with args.output.open("a") as out:
            out.write(line + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
