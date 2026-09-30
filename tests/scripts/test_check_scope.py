"""scripts/check_scope.py against a throwaway git repo (card 001, action 2)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.scripts._load import ROOT, load

scope = load("scripts/check_scope.py")

LOG = scope.LOG
HEADER = "| # | Date | Decision | Status | Recorded in |\n|---|---|---|---|---|\n"
ROW_1 = "| 1 | 2026-09-23 | Everything on Modal | current | ADR-9 |\n"
ROW_2 = "| 2 | 2026-09-23 | A local worker | current | ADR-6 |\n"
BASE_LOG = (
    f"# 10: Decision log\n\nLast updated: 2026-09-29.\n\n## Platform\n\n{HEADER}{ROW_1}{ROW_2}"
)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repo whose `origin/main` holds scopes.toml, the log and one file per area."""
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "test@example.com")
    git(tmp_path, "config", "user.name", "test")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "scopes.toml").write_text((ROOT / "scripts/scopes.toml").read_text())
    (tmp_path / "docs" / "studio").mkdir(parents=True)
    (tmp_path / LOG).write_text(BASE_LOG)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("x = 1\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "base")
    git(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(tmp_path, "checkout", "-q", "-b", "x0/tooling")
    return tmp_path


def run(repo: Path, branch: str = "x0/tooling") -> tuple[list[str], str]:
    problems, summary = scope.check(repo, branch, "origin/main")
    return problems, summary


def test_in_scope_change_passes(repo: Path) -> None:
    (repo / "scripts" / "check.sh").write_text("#!/bin/sh\n")  # untracked, still counted
    (repo / "docs" / "reports").mkdir()
    (repo / "docs" / "reports" / "001-x0-2026-09-30.md").write_text("report\n")
    problems, summary = run(repo)
    assert problems == []
    assert "2 changed files" in summary


def test_out_of_scope_file_fails_with_its_path(repo: Path) -> None:
    (repo / "src" / "app.py").write_text("x = 2\n")
    problems, _ = run(repo)
    assert problems == ["src/app.py: outside x0/'s scope"]


def test_committed_changes_count_too(repo: Path) -> None:
    (repo / "src" / "app.py").write_text("x = 2\n")
    git(repo, "commit", "-qam", "edit")
    problems, _ = run(repo)
    assert problems == ["src/app.py: outside x0/'s scope"]


def test_another_streams_report_is_out_of_scope(repo: Path) -> None:
    (repo / "docs" / "reports").mkdir()
    (repo / "docs" / "reports" / "002-s1-2026-09-30.md").write_text("report\n")
    problems, _ = run(repo)
    assert problems == ["docs/reports/002-s1-2026-09-30.md: outside x0/'s scope"]


def test_deny_wins_over_allow(repo: Path) -> None:
    (repo / ".claude" / "skills" / "neon").mkdir(parents=True)
    (repo / ".claude" / "skills" / "neon" / "SKILL.md").write_text("x\n")
    problems, _ = run(repo)
    assert problems == [".claude/skills/neon/SKILL.md: outside x0/'s scope"]


def test_appended_log_row_in_range_passes(repo: Path) -> None:
    row = "| 380 | 2026-09-30 | check.sh is the single gate | current | card 001 |\n"
    (repo / LOG).write_text(BASE_LOG.replace("2026-09-29.", "2026-09-30.") + row)
    problems, _ = run(repo)
    assert problems == []


def test_log_row_outside_range_fails(repo: Path) -> None:
    (repo / LOG).write_text(BASE_LOG + "| 200 | 2026-09-30 | an S1 row | current | S1 |\n")
    problems, _ = run(repo)
    assert problems == [f"{LOG}: row #200 is outside x0/'s range #380-#399"]


def test_edited_log_row_fails(repo: Path) -> None:
    (repo / LOG).write_text(BASE_LOG.replace("Everything on Modal", "Everything on AWS"))
    problems, _ = run(repo)
    assert problems == [f"{LOG}: row #1 was edited (only its status may change)"]


def test_deleted_log_row_fails(repo: Path) -> None:
    (repo / LOG).write_text(BASE_LOG.replace(ROW_2, ""))
    problems, _ = run(repo)
    assert len(problems) == 1
    assert "removed or edited an existing line" in problems[0]


def test_rewritten_log_fails(repo: Path) -> None:
    (repo / LOG).write_text("# 10: Decision log\n\n" + HEADER + ROW_1)
    problems, _ = run(repo)
    assert problems  # the 2026-09-29 failure: a whole-file rewrite dropped rows


def test_superseding_a_row_with_an_appended_row_passes(repo: Path) -> None:
    new = BASE_LOG.replace("A local worker | current", "A local worker | superseded by 381")
    new += "| 381 | 2026-09-30 | No local worker | current | card 001 |\n"
    (repo / LOG).write_text(new)
    problems, _ = run(repo)
    assert problems == []


def test_superseded_by_a_row_not_appended_here_fails(repo: Path) -> None:
    (repo / LOG).write_text(
        BASE_LOG.replace("A local worker | current", "A local worker | superseded by 1")
    )
    problems, _ = run(repo)
    assert problems == [
        f"{LOG}: row #2's status may only become 'superseded by N' for a row N appended on "
        "this branch"
    ]


def test_duplicate_row_number_fails(repo: Path) -> None:
    (repo / LOG).write_text(BASE_LOG + "| 2 | 2026-09-30 | again | current | x |\n")
    problems, _ = run(repo)
    assert problems == [f"{LOG}: row #2 already exists"]


def test_main_is_exempt(repo: Path) -> None:
    (repo / "src" / "app.py").write_text("x = 2\n")
    problems, summary = run(repo, "main")
    assert problems == []
    assert "exempt" in summary


def test_unknown_prefix_fails(repo: Path) -> None:
    problems, _ = run(repo, "feature/x")
    assert len(problems) == 1
    assert "no prefix in scripts/scopes.toml" in problems[0]


def test_main_cli_exit_codes(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert scope.main(["--repo", str(repo), "--branch", "x0/tooling"]) == 0
    (repo / "src" / "app.py").write_text("x = 2\n")
    assert scope.main(["--repo", str(repo), "--branch", "x0/tooling"]) == 1
    assert "src/app.py: outside x0/'s scope" in capsys.readouterr().err
    assert scope.main(["--repo", str(repo), "--stream-of", "s3c/revision"]) == 0
    assert capsys.readouterr().out.strip() == "s3c"
    assert scope.main(["--repo", str(repo), "--stream-of", "nope/x"]) == 2


@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        (".claude/**", ".claude/hooks/x.py", True),
        ("docs/superpowers/**/*s1*", "docs/superpowers/plans/2026-09-29-studio-s1.md", True),
        ("docs/superpowers/**/*s1*", "docs/superpowers/s1.md", True),
        (
            "docs/superpowers/specs/*s3-workspaces*",
            "docs/superpowers/specs/a/s3-workspaces.md",
            False,
        ),
        ("scripts/**", "scripts/check.sh", True),
        ("CLAUDE.md", "docs/CLAUDE.md", False),
        ("src/**", "srcx/a.py", False),
    ],
)
def test_glob_match(pattern: str, path: str, expected: bool) -> None:
    assert scope.glob_match(pattern, path) is expected


def test_every_card_branch_has_a_scope() -> None:
    scopes = scope.load_scopes(ROOT / "scripts" / "scopes.toml")
    for card in sorted((ROOT / "docs" / "cards").glob("[0-9]*.md")):
        text = card.read_text()
        branch = text.split("Branch: `", 1)[1].split("`", 1)[0]
        assert scope.scope_for(branch, scopes) is not None, f"{card.name}: {branch}"
