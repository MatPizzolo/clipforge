"""The .claude/hooks/ scripts: sample stdin JSON in, exit code and output checked (card 001, 9)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from tests.scripts._load import ROOT, load

bash_guard = load(".claude/hooks/bash_guard.py")
scope_guard = load(".claude/hooks/scope_guard.py")
session_context = load(".claude/hooks/session_context.py")
HOOKS = ROOT / ".claude" / "hooks"


def run_hook(
    name: str, event: object, project: Path | None = None
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ}
    if project is not None:
        env["CLAUDE_PROJECT_DIR"] = str(project)
    stdin = event if isinstance(event, str) else json.dumps(event)
    return subprocess.run(
        ["python3", str(HOOKS / name)], input=stdin, capture_output=True, text=True, env=env
    )


def decision(result: subprocess.CompletedProcess[str]) -> dict[str, str] | None:
    assert result.returncode == 0, result.stderr
    if not result.stdout.strip():
        return None
    output: dict[str, dict[str, str]] = json.loads(result.stdout)
    return output["hookSpecificOutput"]


# --- bash_guard ----------------------------------------------------------------------------

BLOCKED = [
    "git commit -m 'x'",
    "git -C /tmp/repo commit -am x",
    "git push -u origin x0/tooling",
    "git merge main",
    "git tag deploy-1",
    "git rebase main",
    "git reset --hard HEAD~1",
    "git checkout -- .",
    "git clean -fd",
    "git clean --force",
    "cd web && git commit -m x",
    "uv run pytest -q; git push",
    "bash -c 'git commit -m x'",
    'sh -c "git push"',
    "eval git push",
    "GIT_SHA=abc git commit -m x",
    "gh pr merge 3 --squash",
    "gh repo create x",
    "gh secret set X",
    "gh variable set DEPLOY_ENABLED --body true",
    "modal deploy src/clipforge/app.py",
    "uv run modal deploy src/clipforge/app.py",
    "uv run --with x modal deploy src/clipforge/app.py",
    "python -m modal deploy src/clipforge/app.py",
    "uv run modal app stop clipforge",
    "modal secret create clipforge-secrets --force",
    "uv run modal volume rm clipforge-jobs /x",
    "vercel deploy --prod",
    "npx vercel --prod",
    "vercel env add AUTH_SECRET production",
    "scripts/deploy.sh --reason now",
    "uv run python scripts/deploy.py --reason now",
    "cat .env",
    "cat ./.env | head",
    "less web/.env.local",
    "grep API_TOKEN .env",
    "tail -n 5 /home/x/clipForge/.env",
    "source .env",
    ". .env",
    "cat .neon",
    "sed -n 1p .env",
    "while read l; do echo $l; done < .env",
    "echo $(cat .env)",
    # after a quoted heredoc, the shell runs commands again
    "cat > notes.md <<'EOF'\nrun `modal deploy` later\nEOF\ngit commit -am notes",
    # an unquoted heredoc expands $(...), so its body is still checked
    "cat > x.txt <<EOF\n$(git push)\nEOF",
    # inside double quotes, substitutions run
    'echo "now: $(git push)"',
    'echo "now: `git push`"',
]

ALLOWED = [
    "git status",
    "git status --short",
    "git diff --stat",
    "git log --oneline -5",
    "git show HEAD:README.md",
    "git ls-files",
    "git branch --show-current",
    "git fetch origin",
    "git tag",
    "git tag -l 'deploy-*'",
    "git checkout -- STATUS.md",
    "git add -A --dry-run",
    "scripts/check.sh",
    "scripts/check.sh --python --docs",
    "uv run python scripts/check_scope.py",
    "scripts/deploy.sh --dry-run",
    "uv run modal run src/clipforge/app.py::doctor",
    "modal app list",
    "gh pr view 3",
    "gh run list --limit 5",
    "cat .env.example",
    "grep -n POSTING .env.example",
    "cp .env ../clipForge-s1/",
    "ls -la .env",
    "echo 'git commit is the owner job'",
    "uv run pytest -q tests/scripts",
    "npm --prefix web run check",
    # a quoted heredoc's body is text, never run (agent and doc files mention these commands)
    "cat > a.md <<'EOF'\nOnly the owner runs `modal deploy`, `git commit`; not `cat .env`.\nEOF",
    # single-quoted text is never run either
    "sed -i 's|run `modal deploy` here|x|' notes.md",
    "echo 'git push; git commit'",
    "grep -n 'git commit\\|modal deploy' CLAUDE.md",
    'cat > b.md <<"END"\ngit push origin main\nEND\nls',
    "cat > c.md <<-'EOF'\n\tgit commit\n\tEOF",
]


@pytest.mark.parametrize("command", BLOCKED)
def test_bash_guard_blocks(command: str) -> None:
    assert bash_guard.command_problem(command) is not None


@pytest.mark.parametrize("command", ALLOWED)
def test_bash_guard_allows(command: str) -> None:
    assert bash_guard.command_problem(command) is None


def test_bash_guard_denies_through_stdin_with_a_reason() -> None:
    event = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
             "tool_input": {"command": "git commit -m x"}}  # fmt: skip
    out = decision(run_hook("bash_guard.py", event))
    assert out is not None
    assert out["hookEventName"] == "PreToolUse"
    assert out["permissionDecision"] == "deny"
    assert "`git commit`" in out["permissionDecisionReason"]
    assert "owner" in out["permissionDecisionReason"]


def test_bash_guard_allows_through_stdin_silently() -> None:
    event = {"tool_name": "Bash", "tool_input": {"command": "git status"}}
    assert decision(run_hook("bash_guard.py", event)) is None


@pytest.mark.parametrize("stdin", ["", "not json", "[]", '{"tool_input": {"command": 3}}'])
def test_bash_guard_never_blocks_on_bad_input(stdin: str) -> None:
    result = run_hook("bash_guard.py", stdin)
    assert result.returncode == 0
    assert result.stdout == ""


# --- scope_guard ---------------------------------------------------------------------------


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repo on branch x0/tooling with the real scopes.toml and check_scope.py."""
    (tmp_path / "scripts").mkdir()
    for name in ("scopes.toml", "check_scope.py", "tree_hash.sh"):
        shutil.copy2(ROOT / "scripts" / name, tmp_path / "scripts" / name)
    (tmp_path / "docs" / "studio").mkdir(parents=True)
    (tmp_path / "docs" / "studio" / "10-decision-log.md").write_text("# log\n")
    (tmp_path / "docs" / "cards").mkdir()
    (tmp_path / "docs" / "cards" / "001-x0-tooling.md").write_text(
        "# Card 001: X0 — tooling\n\nStatus: sent\n"
        "Stream: X0 · Branch: `x0/tooling` · Worktree: `../clipForge-x0`\n"
        "Decision-log range: #380\u2013#399\n\n## Scope\n- May edit: scripts/\n\n"
        "## Actions\n1. x\n\n## Checkpoints\n- A: actions 1-3.\n"
    )
    (tmp_path / "STATUS.md").write_text(
        "# Status\n\n## Next cards (in order)\n\n| Card | What |\n|---|---|\n| 001 | X0 |\n\n"
        "## Workstreams\nlots\n"
    )
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "base")
    git(tmp_path, "checkout", "-q", "-b", "x0/tooling")
    return tmp_path


def edit_event(tool: str, path: str) -> dict[str, object]:
    key = "notebook_path" if tool == "NotebookEdit" else "file_path"
    return {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": {key: path}}


@pytest.mark.parametrize(
    ("tool", "path"),
    [
        ("Edit", "scripts/check.sh"),
        ("Write", ".claude/hooks/new.py"),
        ("Edit", "docs/studio/10-decision-log.md"),
        ("Write", "docs/reports/001-x0-2026-09-30.md"),
        ("MultiEdit", "tests/scripts/test_x.py"),
        ("Write", "/tmp/elsewhere/scratch.py"),
    ],
)
def test_scope_guard_allows_in_scope_and_outside_the_repo(repo: Path, tool: str, path: str) -> None:
    target = path if path.startswith("/") else str(repo / path)
    assert decision(run_hook("scope_guard.py", edit_event(tool, target), repo)) is None


@pytest.mark.parametrize(
    ("tool", "path", "why"),
    [
        ("Edit", "src/clipforge/app.py", "outside the scope of x0/tooling"),
        ("NotebookEdit", "notebooks/a.ipynb", "outside the scope"),
        ("Write", ".claude/skills/neon/SKILL.md", "outside the scope"),
        ("Write", "docs/studio/10-decision-log.md", "append-only"),
        ("Edit", ".env", "holds secrets"),
        ("Write", ".env.production", "holds secrets"),
        ("Edit", "web/.env.local", "holds secrets"),
        ("Edit", ".neon", "holds secrets"),
        ("Edit", ".claude/settings.local.json", "holds secrets"),
        ("Write", "/tmp/other/.env", "holds secrets"),
    ],
)
def test_scope_guard_denies(repo: Path, tool: str, path: str, why: str) -> None:
    target = path if path.startswith("/") else str(repo / path)
    out = decision(run_hook("scope_guard.py", edit_event(tool, target), repo))
    assert out is not None
    assert out["permissionDecision"] == "deny"
    assert why in out["permissionDecisionReason"]


def test_scope_guard_allows_env_example(repo: Path) -> None:
    event = edit_event("Edit", str(repo / ".env.example"))
    git(repo, "checkout", "-q", "-b", "s1/finish")  # .env.example is in s1/'s scope
    assert decision(run_hook("scope_guard.py", event, repo)) is None


def test_scope_guard_on_main_allows_only_coord_paths(repo: Path) -> None:
    git(repo, "checkout", "-q", "main")
    assert (
        decision(run_hook("scope_guard.py", edit_event("Edit", str(repo / "STATUS.md")), repo))
        is None
    )
    out = decision(
        run_hook("scope_guard.py", edit_event("Edit", str(repo / "scripts/check.sh")), repo)
    )
    assert out is not None
    assert "main (the coordinator's checkout" in out["permissionDecisionReason"]


def test_scope_guard_denies_an_unknown_prefix(repo: Path) -> None:
    git(repo, "checkout", "-q", "-b", "feature/x")
    out = decision(run_hook("scope_guard.py", edit_event("Edit", str(repo / "scripts/x.sh")), repo))
    assert out is not None
    assert "no prefix in scripts/scopes.toml" in out["permissionDecisionReason"]


@pytest.mark.parametrize("stdin", ["", "{}", '{"tool_input": {}}', "nope"])
def test_scope_guard_never_blocks_on_bad_input(repo: Path, stdin: str) -> None:
    result = run_hook("scope_guard.py", stdin, repo)
    assert result.returncode == 0
    assert result.stdout == ""


# --- session_context -----------------------------------------------------------------------


def context(result: subprocess.CompletedProcess[str]) -> str:
    out = decision(result)
    assert out is not None
    assert out["hookEventName"] == "SessionStart"
    return out["additionalContext"]


@pytest.mark.parametrize("source", ["startup", "resume", "compact"])
def test_session_context_names_the_card(repo: Path, source: str) -> None:
    text = context(run_hook("session_context.py", {"source": source}, repo))
    assert f"({source})" in text
    assert "Branch: x0/tooling" in text
    assert "docs/cards/001-x0-tooling.md" in text
    assert "Decision-log range: #380\u2013#399" in text
    assert "May edit: scripts/" in text
    assert "| 001 | X0 |" in text  # STATUS.md's next cards
    assert "lots" not in text  # ...and nothing after them
    assert "Never commit" in text


def test_session_context_warns_on_main(repo: Path) -> None:
    git(repo, "checkout", "-q", "main")
    text = context(run_hook("session_context.py", {"source": "startup"}, repo))
    assert "WARNING: this is main" in text


def test_session_context_says_when_no_card_matches(repo: Path) -> None:
    git(repo, "checkout", "-q", "-b", "s4/timeline")
    text = context(run_hook("session_context.py", {"source": "startup"}, repo))
    assert "No card in docs/cards/ names branch `s4/timeline`" in text


def test_session_context_is_silent_outside_a_repo(tmp_path: Path) -> None:
    result = run_hook("session_context.py", {"source": "startup"}, tmp_path)
    assert result.returncode == 0
    assert result.stdout == ""


# --- stop_check ----------------------------------------------------------------------------


def stop(repo: Path, active: bool = False) -> dict[str, str] | None:
    result = run_hook(
        "stop_check.py", {"hook_event_name": "Stop", "stop_hook_active": active}, repo
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout) if result.stdout.strip() else None


def test_stop_allows_when_nothing_changed(repo: Path) -> None:
    assert stop(repo) is None


def test_stop_blocks_once_when_files_changed_without_a_green_check(repo: Path) -> None:
    (repo / "scripts" / "new.sh").write_text("echo\n")
    out = stop(repo)
    assert out is not None
    assert out["decision"] == "block"
    assert "scripts/check.sh" in out["reason"]
    assert stop(repo, active=True) is None  # never loops


@pytest.mark.parametrize(
    ("branch", "asks_for_report"),
    [("x0/tooling", True), ("main", False), ("coord/card-008", False)],
)
def test_stop_asks_for_a_report_only_on_card_branches(
    repo: Path, branch: str, asks_for_report: bool
) -> None:
    """Card 008: the coordinator (main, coord/) has no card report, but still runs check.sh."""
    if branch != "x0/tooling":
        git(repo, "checkout", "-q", "-B", branch)
    (repo / "scripts" / "new.sh").write_text("echo\n")
    out = stop(repo)
    assert out is not None
    assert out["decision"] == "block"
    assert "Run scripts/check.sh until it's green" in out["reason"]
    assert ("docs/reports/" in out["reason"]) is asks_for_report


def test_stop_allows_after_a_green_check_until_the_next_change(repo: Path) -> None:
    (repo / "STATUS.md").write_text("changed\n")
    marker = repo / ".superpowers" / "check-ok"
    marker.parent.mkdir()
    (repo / ".gitignore").write_text(".superpowers/\n")
    tree = subprocess.run(
        [str(repo / "scripts" / "tree_hash.sh")], cwd=repo, capture_output=True, text=True
    )
    marker.write_text(tree.stdout)
    assert stop(repo) is None
    (repo / "STATUS.md").write_text("changed again\n")
    assert stop(repo) is not None


def test_stop_does_not_touch_the_real_index(repo: Path) -> None:
    (repo / "untracked.txt").write_text("x\n")
    stop(repo)
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True
    ).stdout
    assert "?? untracked.txt" in status  # still untracked: nothing was staged


# --- speed ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "event"),
    [
        ("bash_guard.py", {"tool_name": "Bash", "tool_input": {"command": "git status"}}),
        ("scope_guard.py", {"tool_name": "Edit", "tool_input": {"file_path": "scripts/x.sh"}}),
        ("session_context.py", {"source": "startup"}),
        ("stop_check.py", {"stop_hook_active": False}),
    ],
)
def test_hooks_are_fast(repo: Path, name: str, event: dict[str, object]) -> None:
    run_hook(name, event, repo)  # warm the filesystem cache
    started = time.perf_counter()
    run_hook(name, event, repo)
    assert time.perf_counter() - started < 1.0  # target ~200 ms; generous for slow CI disks
