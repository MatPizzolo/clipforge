"""Fail when a branch changes files outside its card's scope (card 001, decision log #127).

The allowed paths per branch prefix live in scripts/scopes.toml. Changes are the working tree
(committed, staged, unstaged and untracked files) against the merge base with `origin/main`, so
the same check works in a session before the owner commits and in CI on the pull request.
During an uncommitted merge (MERGE_HEAD exists), the base is the one the merge commit will have
with `origin/main`, so the files the merge brings in from `main` don't count (card 013).

The decision log (docs/studio/10-decision-log.md) is append-only on every branch: added rows must
fall in the branch's number range, and an existing row may only change its status to
"superseded by N" for a row N that the same branch appends.

    uv run python scripts/check_scope.py                 # the current branch
    uv run python scripts/check_scope.py --stream-of s1/finish   # prints "s1", exit 2 if unknown
"""

from __future__ import annotations

import argparse
import difflib
import os
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = "docs/studio/10-decision-log.md"
EXEMPT_BRANCHES = ("main",)

_ROW = re.compile(r"^\|\s*(\d+)\s*\|")
_OPEN_ROW = re.compile(r"^\|\s*O\d+\s*\|")
_SUPERSEDED = re.compile(r"superseded(?: in part)? by (\d+)")


@dataclass(frozen=True)
class Scope:
    prefix: str
    stream: str
    log: tuple[int, int]
    allow: tuple[str, ...]
    deny: tuple[str, ...] = ()

    def in_range(self, number: int) -> bool:
        return self.log[0] <= number <= self.log[1]


def load_scopes(path: Path) -> dict[str, Scope]:
    data = tomllib.loads(path.read_text())
    scopes = {}
    for prefix, entry in data.get("prefix", {}).items():
        low, high = entry["log"]
        scopes[prefix] = Scope(
            prefix=prefix,
            stream=entry["stream"],
            log=(int(low), int(high)),
            allow=tuple(entry.get("allow", ())),
            deny=tuple(entry.get("deny", ())),
        )
    return scopes


def scope_for(branch: str, scopes: dict[str, Scope]) -> Scope | None:
    for prefix, scope in scopes.items():
        if branch.startswith(prefix):
            return scope
    return None


@cache
def _glob_regex(pattern: str) -> re.Pattern[str]:
    out = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def glob_match(pattern: str, path: str) -> bool:
    return _glob_regex(pattern).match(path) is not None


def path_allowed(scope: Scope, path: str) -> bool:
    """Whether the branch may change `path` at all. The decision log is always allowed here;
    its content is checked by `log_problems`."""
    if path == LOG:
        return True
    if glob_match(f"docs/reports/*-{scope.stream}-*", path):
        return True
    if any(glob_match(pattern, path) for pattern in scope.deny):
        return False
    return any(glob_match(pattern, path) for pattern in scope.allow)


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _row_number(line: str) -> int | None:
    match = _ROW.match(line)
    return int(match.group(1)) if match else None


def log_problems(scope: Scope, old: str, new: str) -> list[str]:
    """Why the change from `old` to `new` isn't an in-range append, or [] when it is."""
    old_lines, new_lines = old.splitlines(), new.splitlines()
    existing = {n for line in old_lines if (n := _row_number(line)) is not None}
    added_rows: set[int] = set()
    problems: list[str] = []
    status_changes: list[tuple[str, str]] = []
    coord = scope.stream == "coord"

    def check_added(line: str) -> None:
        if not line.strip():
            return
        number = _row_number(line)
        if number is None:
            if coord and _OPEN_ROW.match(line):
                return
            problems.append(f"added a line that isn't a numbered row: {line[:80]!r}")
        elif number in existing or number in added_rows:
            problems.append(f"row #{number} already exists")
        elif not scope.in_range(number):
            low, high = scope.log
            problems.append(f"row #{number} is outside {scope.prefix}'s range #{low}-#{high}")
        else:
            added_rows.add(number)

    def check_removed(line: str) -> None:
        if not line.strip() or (coord and _OPEN_ROW.match(line)):
            return
        problems.append(f"removed or edited an existing line: {line[:80]!r}")

    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        removed, added = old_lines[i1:i2], new_lines[j1:j2]
        # Pair edited lines one to one; the rest are plain removals or additions.
        pairs = list(zip(removed, added, strict=False)) if tag == "replace" else []
        for before, after in pairs:
            if before.startswith("Last updated:") and after.startswith("Last updated:"):
                continue
            number = _row_number(before)
            if number is not None and number == _row_number(after):
                status_changes.append((before, after))
            else:
                check_removed(before)
                check_added(after)
        for line in removed[len(pairs) :]:
            check_removed(line)
        for line in added[len(pairs) :]:
            check_added(line)

    for before, after in status_changes:
        old_cells, new_cells = _cells(before), _cells(after)
        number = old_cells[0]
        same_except_status = len(old_cells) == len(new_cells) and all(
            a == b for k, (a, b) in enumerate(zip(old_cells, new_cells, strict=True)) if k != 3
        )
        superseded = _SUPERSEDED.search(new_cells[3]) if len(new_cells) > 3 else None
        if not same_except_status:
            problems.append(f"row #{number} was edited (only its status may change)")
        elif superseded is None or int(superseded.group(1)) not in added_rows:
            problems.append(
                f"row #{number}'s status may only become 'superseded by N' for a row N "
                "appended on this branch"
            )
    return problems


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return result.stdout


def current_branch(repo: Path) -> str:
    return os.environ.get("GITHUB_HEAD_REF") or _git(repo, "branch", "--show-current").strip()


def changed_files(repo: Path, base: str) -> list[str]:
    tracked = _git(repo, "diff", "--name-only", "--no-renames", base).splitlines()
    untracked = _git(repo, "ls-files", "--others", "--exclude-standard").splitlines()
    return sorted(set(tracked) | set(untracked))


def _file_at(repo: Path, rev: str, path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{rev}:{path}"], cwd=repo, capture_output=True, text=True
    )
    return result.stdout if result.returncode == 0 else ""


def merge_in_progress(repo: Path) -> bool:
    merge_head = _git(repo, "rev-parse", "--git-path", "MERGE_HEAD").strip()
    return (repo / merge_head).exists()


def diff_base(repo: Path, base_ref: str) -> str:
    """The commit to diff the working tree against: the merge base with `base_ref`, or during
    a merge the merge base of `base_ref` with the merge of HEAD and MERGE_HEAD (git merge-base
    treats its first argument apart from the rest)."""
    if merge_in_progress(repo):
        print(
            f"merge in progress: checking against the merge base of HEAD, MERGE_HEAD and {base_ref}"
        )
        return _git(repo, "merge-base", base_ref, "HEAD", "MERGE_HEAD").strip()
    return _git(repo, "merge-base", base_ref, "HEAD").strip()


def check(repo: Path, branch: str, base_ref: str) -> tuple[list[str], str]:
    """(problems, summary) for `branch` in `repo` against `base_ref`."""
    if branch in EXEMPT_BRANCHES:
        return [], f"scope: {branch} is exempt"
    scopes = load_scopes(repo / "scripts" / "scopes.toml")
    scope = scope_for(branch, scopes)
    if scope is None:
        known = ", ".join(sorted(scopes))
        return [f"branch {branch!r} has no prefix in scripts/scopes.toml ({known})"], ""
    base = diff_base(repo, base_ref)
    files = changed_files(repo, base)
    problems = [
        f"{path}: outside {scope.prefix}'s scope" for path in files if not path_allowed(scope, path)
    ]
    if LOG in files:
        new_path = repo / LOG
        new = new_path.read_text() if new_path.exists() else ""
        problems += [f"{LOG}: {p}" for p in log_problems(scope, _file_at(repo, base, LOG), new)]
    summary = (
        f"scope: {len(files)} changed files against {base_ref} (merge base {base[:7]}), "
        f"all in {scope.prefix}'s scope"
    )
    return problems, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check that a branch stays in its scope.")
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--base", default="origin/main", help="the ref to diff against")
    parser.add_argument("--branch", help="default: $GITHUB_HEAD_REF or the current branch")
    parser.add_argument("--stream-of", metavar="BRANCH", help="print the stream of BRANCH")
    args = parser.parse_args(argv)

    if args.stream_of:
        scope = scope_for(args.stream_of, load_scopes(args.repo / "scripts" / "scopes.toml"))
        if scope is None:
            print(f"no prefix in scripts/scopes.toml matches {args.stream_of!r}", file=sys.stderr)
            return 2
        print(scope.stream)
        return 0

    branch = args.branch or current_branch(args.repo)
    if not branch:
        print("scope: no branch (detached HEAD); pass --branch", file=sys.stderr)
        return 2
    problems, summary = check(args.repo, branch, args.base)
    if problems:
        print(f"scope: {len(problems)} problem(s) on {branch}:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        print(
            "Fix the change, or ask the coordinator to widen scripts/scopes.toml.", file=sys.stderr
        )
        return 1
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
