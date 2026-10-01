"""The derived producer version (draft ADR-43)."""

from __future__ import annotations

import re
from pathlib import Path

from clipforge.config import Settings
from clipforge.stages.runner import producer_version


def _settings(tmp_path: Path, **overrides: str) -> Settings:
    return Settings(_env_file=None, jobs_root=tmp_path, **overrides)  # type: ignore[arg-type]


def test_producer_version_is_pinned(tmp_path: Path) -> None:
    # bump deliberately: changes when a stage version, prompt or model changes
    # (clips:14fcf790 -> clips:4c44b731 at render STAGE_VERSION 4, card 006, spec §7)
    assert producer_version(_settings(tmp_path)) == "clips:4c44b731"


def test_producer_version_shape(tmp_path: Path) -> None:
    assert re.fullmatch(r"clips:[0-9a-f]{8}", producer_version(_settings(tmp_path)))


def test_a_model_change_changes_it(tmp_path: Path) -> None:
    base = producer_version(_settings(tmp_path))
    assert producer_version(_settings(tmp_path, highlight_model="claude-sonnet-4-5")) != base


def test_the_git_sha_does_not_change_it(tmp_path: Path) -> None:
    assert producer_version(_settings(tmp_path, git_sha="abc")) == producer_version(
        _settings(tmp_path)
    )
