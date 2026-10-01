#!/usr/bin/env python3
"""PreToolUse guard for Edit, Write, MultiEdit and NotebookEdit (card 001, action 9; log #130).

Denies:
- an edit to a path the current branch prefix may not touch (scripts/scopes.toml, the same rules
  as scripts/check_scope.py); on `main` (the coordinator's checkout) only `coord/` paths;
- any edit to secrets files: .env and .env.* (not .env.example), .neon, web/.env.local, and
  .claude/settings.local.json;
- a Write (full overwrite) of docs/studio/10-decision-log.md: add rows with Edit instead.
Paths outside the repo (the scratchpad, memory) aren't governed, except secrets files.
A crash or unparseable input never blocks: only an explicit match does.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType


def _load_check_scope(root: Path) -> ModuleType:
    path = root / "scripts" / "check_scope.py"
    spec = importlib.util.spec_from_file_location("_clipforge_check_scope", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def is_secret_file(rel_or_abs: str) -> bool:
    parts = rel_or_abs.replace("\\", "/").rstrip("/").split("/")
    name = parts[-1]
    if name in (".env", ".neon") or (name.startswith(".env.") and name != ".env.example"):
        return True
    return parts[-2:] == [".claude", "settings.local.json"]


def decide(tool: str, file_path: str, root: Path, branch: str) -> str | None:
    """Why this edit is denied, or None to allow it."""
    target = Path(file_path)
    if not target.is_absolute():
        target = root / target
    target = Path(os.path.normpath(target))
    if is_secret_file(str(target)):
        return f"{file_path} holds secrets: only the owner edits it."
    try:
        rel = target.relative_to(root).as_posix()
    except ValueError:
        return None  # outside the repo
    check_scope = _load_check_scope(root)
    if rel == check_scope.LOG and tool == "Write":
        return (
            f"{rel} is append-only: never overwrite it with Write. Re-read it, then add rows "
            "with Edit after the last row, in your branch's number range."
        )
    scopes = check_scope.load_scopes(root / "scripts" / "scopes.toml")
    if branch == "main":
        scope = scopes.get("coord/")
        where = "main (the coordinator's checkout: coord/ paths only)"
    else:
        scope = check_scope.scope_for(branch, scopes)
        where = branch
    if scope is None:
        return (
            f"branch {branch or '(detached)'} has no prefix in scripts/scopes.toml, so no edit "
            "is in scope. Work on the card's branch (scripts/worktree.sh <branch>)."
        )
    if not check_scope.path_allowed(scope, rel):
        return (
            f"{rel} is outside the scope of {where} (scripts/scopes.toml). Leave it, or ask the "
            "owner: a scope change is a coord/ change."
        )
    return None


def _repo_root(cwd: str) -> Path | None:
    start = os.environ.get("CLAUDE_PROJECT_DIR") or cwd or "."
    result = subprocess.run(
        ["git", "-C", start, "rev-parse", "--show-toplevel"], capture_output=True, text=True
    )
    return Path(result.stdout.strip()) if result.returncode == 0 else None


def _branch(root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "branch", "--show-current"], capture_output=True, text=True
    )
    return result.stdout.strip()


def main() -> int:
    try:
        event = json.load(sys.stdin)
        tool = event.get("tool_name", "")
        tool_input = event.get("tool_input", {})
        file_path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
        if not file_path:
            return 0
        root = _repo_root(event.get("cwd", ""))
        if root is None or not (root / "scripts" / "scopes.toml").is_file():
            return 0
        reason = decide(tool, file_path, root, _branch(root))
    except Exception:  # never block on a bug here
        return 0
    if reason is None:
        return 0
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": "Blocked by .claude/hooks/scope_guard.py: "
                    + reason,
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
