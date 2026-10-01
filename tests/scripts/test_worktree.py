"""scripts/worktree.sh in a throwaway clone with a bare origin (card 001, action 5)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from tests.scripts._load import ROOT


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)


def worktree(clone: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["scripts/worktree.sh", "--no-deps", *args], cwd=clone, capture_output=True, text=True
    )


@pytest.fixture
def clone(tmp_path: Path) -> Path:
    """<tmp>/clipForge: a clone of a bare origin whose main has the scripts and one s1 card."""
    seed = tmp_path / "seed"
    (seed / "scripts").mkdir(parents=True)
    for name in ("worktree.sh", "check_scope.py", "scopes.toml"):
        shutil.copy2(ROOT / "scripts" / name, seed / "scripts" / name)
    (seed / "docs" / "cards").mkdir(parents=True)
    # The real cards' header format: Branch and Worktree mid-line.
    (seed / "docs" / "cards" / "002-s1-finish.md").write_text(
        "# Card 002\n\nStatus: proposed\n"
        "Stream: S1 · Branch: `s1/finish` · Worktree: `../clipForge-s1`\n"
    )
    (seed / "docs" / "cards" / "004-s3a-deploy.md").write_text(
        "# Card 004\n\nStatus: proposed\n"
        "Stream: S3a · Branch: `s3a/deploy` · Worktree: `../clipForge-web`\n"
    )
    (seed / ".gitignore").write_text(".env\n")
    for args in (
        ("init", "-q", "-b", "main"),
        ("config", "user.email", "test@example.com"),
        ("config", "user.name", "test"),
        ("add", "-A"),
        ("commit", "-q", "-m", "base"),
    ):
        assert git(seed, *args).returncode == 0
    subprocess.run(
        ["git", "clone", "-q", "--bare", str(seed), str(tmp_path / "origin.git")], check=True
    )
    subprocess.run(
        ["git", "clone", "-q", str(tmp_path / "origin.git"), str(tmp_path / "clipForge")],
        check=True,
    )
    clone = tmp_path / "clipForge"
    (clone / ".env").write_text("DUMMY=1\n")
    return clone


def test_new_branch_has_no_upstream_and_gets_env_and_hints(clone: Path) -> None:
    result = worktree(clone, "s1/finish")
    assert result.returncode == 0, result.stderr
    path = clone.parent / "clipForge-s1"
    assert (path / ".env").read_text() == "DUMMY=1\n"
    assert git(path, "branch", "--show-current").stdout.strip() == "s1/finish"
    upstream = git(clone, "rev-parse", "--abbrev-ref", "s1/finish@{upstream}")
    assert upstream.returncode != 0, f"s1/finish tracks {upstream.stdout.strip()}"
    assert "Run card docs/cards/002-s1-finish.md" in result.stdout
    assert "git push -u origin s1/finish" in result.stdout


def test_refuses_an_unknown_prefix(clone: Path) -> None:
    result = worktree(clone, "feature/x")
    assert result.returncode == 1
    assert "refused" in result.stderr
    assert not (clone.parent / "clipForge-feature").exists()


def test_refuses_an_existing_path(clone: Path) -> None:
    assert worktree(clone, "s1/finish").returncode == 0
    result = worktree(clone, "s1/other")
    assert result.returncode == 1
    assert "already exists" in result.stderr


def test_remove_refuses_an_unmerged_branch_then_removes_a_merged_one(clone: Path) -> None:
    assert worktree(clone, "s1/finish").returncode == 0
    path = clone.parent / "clipForge-s1"
    for args in (
        ("config", "user.email", "test@example.com"),
        ("config", "user.name", "test"),
        ("commit", "-q", "--allow-empty", "-m", "work"),
    ):
        assert git(path, *args).returncode == 0
    refused = worktree(clone, "--remove", "s1/finish")
    assert refused.returncode == 1
    assert "isn't merged" in refused.stderr

    assert git(path, "push", "-q", "origin", "s1/finish:main").returncode == 0  # "merged"
    removed = worktree(clone, "--remove", "s1/finish")
    assert removed.returncode == 0, removed.stderr
    assert not path.exists()
    assert "git branch -D s1/finish" in removed.stdout


def test_the_cards_worktree_name_wins(clone: Path) -> None:
    result = worktree(clone, "s3a/deploy")
    assert result.returncode == 0, result.stderr
    assert (clone.parent / "clipForge-web").is_dir()
    assert not (clone.parent / "clipForge-s3a").exists()
    assert "Run card docs/cards/004-s3a-deploy.md" in result.stdout


def test_without_a_card_the_stream_names_the_worktree(clone: Path) -> None:
    result = worktree(clone, "s4/timeline")
    assert result.returncode == 0, result.stderr
    assert (clone.parent / "clipForge-s4").is_dir()
    assert "no card names s4/timeline yet" in result.stdout
