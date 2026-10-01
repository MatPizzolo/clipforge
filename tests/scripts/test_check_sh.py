"""scripts/check.sh keeps a failing step's full output (card 008, action 5)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from tests.scripts._load import ROOT


def run_check(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """check.sh from a copy in `repo`, with a fake `uv` that prints 200 lines and fails."""
    (repo / "scripts").mkdir(exist_ok=True)
    shutil.copy2(ROOT / "scripts" / "check.sh", repo / "scripts" / "check.sh")
    bin_dir = repo / "bin"
    bin_dir.mkdir(exist_ok=True)
    fake = bin_dir / "uv"
    fake.write_text(
        '#!/usr/bin/env bash\nfor i in $(seq 1 200); do echo "line $i of $*"; done\nexit 1\n'
    )
    fake.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    return subprocess.run(
        ["bash", str(repo / "scripts" / "check.sh"), *args],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
    )


def test_a_failing_step_keeps_its_full_output(tmp_path: Path) -> None:
    result = run_check(tmp_path, "--python")
    assert result.returncode == 1
    log = tmp_path / ".superpowers" / "check-last-fail.log"
    text = log.read_text()
    assert "# scripts/check.sh: ruff check failed at " in text
    assert "# command: uv run ruff check ." in text
    assert "line 1 of run ruff check ." in text  # the start, which the terminal tail drops
    assert "line 200 of run ruff check ." in text
    assert "line 1 of" not in result.stderr  # the terminal still gets only the last 60 lines
    path = tmp_path / ".superpowers" / "check-last-fail.log"
    assert f"full output of ruff check: {path}" in result.stderr
    assert "FAIL ruff check" in result.stdout
    assert "full output in .superpowers/check-last-fail.log" in result.stdout
    assert not (tmp_path / ".superpowers" / "check-ok").exists()


def test_the_next_failure_replaces_the_log(tmp_path: Path) -> None:
    log = tmp_path / ".superpowers" / "check-last-fail.log"
    log.parent.mkdir()
    log.write_text("an older failure\n")
    run_check(tmp_path, "--docs")
    text = log.read_text()
    assert "an older failure" not in text
    assert "# scripts/check.sh: docs failed at " in text
