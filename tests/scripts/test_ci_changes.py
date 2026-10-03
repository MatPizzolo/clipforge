"""scripts/ci_changes.py: which changes skip the code checks in CI (card 017, action 2)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.scripts._load import load

changes = load("scripts/ci_changes.py")


@pytest.mark.parametrize(
    "path",
    [
        "docs/ARCHITECTURE.md",
        "docs/cards/017-x0-ci-speed.md",
        "docs/design/dashboard/home.png",
        "STATUS.md",
        "ROADMAP.md",
        "README.md",
        "web/README.md",
        ".gitignore",
    ],
)
def test_docs_paths(path: str) -> None:
    assert changes.is_docs(path)
    assert changes.needs_code_checks([path]) is False


@pytest.mark.parametrize(
    "path",
    [
        "src/x.py",
        "scripts/check.sh",
        ".github/workflows/ci.yml",
        "pyproject.toml",
        "uv.lock",
        "web/app/page.tsx",
        "prompts/x_v1.md.bak",
        "prompts/x_v1.md",  # a released prompt is code (CLAUDE.md rule 4), not docs
        "tests/test_docs.py",
        "web/.gitignore",
        "docs",
    ],
)
def test_code_paths(path: str) -> None:
    assert changes.needs_code_checks(["docs/a.md", path]) is True


def test_an_empty_diff_needs_no_code_checks() -> None:
    assert changes.needs_code_checks([]) is False


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "README.md").write_text("x\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "base")
    return tmp_path


def run(repo: Path, base: str, tmp_path: Path, diff: str = "three-dot") -> tuple[str, str]:
    out = tmp_path / "github_output"
    out.write_text("")
    argv = ["--repo", str(repo), "--base", base, "--diff", diff, "--output", str(out)]
    assert changes.main(argv) == 0
    return out.read_text(), base


def test_docs_only_commit_writes_false(repo: Path, tmp_path: Path) -> None:
    base = git(repo, "rev-parse", "HEAD").strip()
    (repo / "README.md").write_text("y\n")
    git(repo, "commit", "-qam", "docs")
    assert run(repo, base, tmp_path)[0] == "code=false\n"


def test_code_commit_writes_true(repo: Path, tmp_path: Path) -> None:
    base = git(repo, "rev-parse", "HEAD").strip()
    (repo / "app.py").write_text("x = 1\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "code")
    assert run(repo, base, tmp_path)[0] == "code=true\n"


@pytest.mark.parametrize("base", ["", "0" * 40, "1234567890abcdef1234567890abcdef12345678"])
def test_a_missing_or_unknown_base_is_code(repo: Path, tmp_path: Path, base: str) -> None:
    assert run(repo, base, tmp_path)[0] == "code=true\n"


def test_two_dot_sees_a_change_that_three_dot_hides(repo: Path, tmp_path: Path) -> None:
    # main's last green commit sits on a side branch that changed code; HEAD left before it.
    # Three dots (merge base to HEAD) see nothing; two dots compare the trees, as deploy does.
    start = git(repo, "rev-parse", "HEAD").strip()
    git(repo, "checkout", "-q", "-b", "side")
    (repo / "app.py").write_text("x = 1\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "code on the side")
    green = git(repo, "rev-parse", "HEAD").strip()
    git(repo, "checkout", "-q", start)
    (repo / "README.md").write_text("docs\n")
    git(repo, "commit", "-qam", "docs")
    assert run(repo, green, tmp_path, "three-dot")[0] == "code=false\n"
    assert run(repo, green, tmp_path, "two-dot")[0] == "code=true\n"
