"""scripts/deploy.py: the blackout calculation and the refusal rules (card 001, action 6)."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from tests.scripts._load import load

deploy = load("scripts/deploy.py")

NY = ZoneInfo("America/New_York")
DEFAULT = ["08:00", "10:30", "13:00", "16:00", "19:00", "21:30"]


def ny(day: int, hour: int, minute: int) -> datetime:
    return datetime(2026, 9, day, hour, minute, tzinfo=NY)


@pytest.mark.parametrize(
    ("now", "blocked"),
    [
        (ny(30, 21, 29), False),
        (ny(30, 21, 30), True),
        (ny(30, 21, 45), True),
        (ny(30, 22, 0), True),
        (ny(30, 22, 1), False),
        (ny(30, 8, 15), True),
        (ny(30, 12, 0), False),
    ],
)
def test_blackout_around_the_2130_slot(now: datetime, blocked: bool) -> None:
    assert (deploy.blackout_slot(DEFAULT, "America/New_York", now) is not None) is blocked


def test_blackout_across_midnight() -> None:
    slots = ["08:00", "23:45"]
    assert deploy.blackout_slot(slots, "America/New_York", ny(30, 0, 10)) == ny(29, 23, 45)
    assert deploy.blackout_slot(slots, "America/New_York", ny(30, 0, 16)) is None


def test_blackout_uses_the_slot_time_zone_whatever_now_is_in() -> None:
    utc_now = ny(30, 21, 45).astimezone(ZoneInfo("UTC"))  # 01:45 UTC on Oct 1
    assert deploy.blackout_slot(DEFAULT, "America/New_York", utc_now) == ny(30, 21, 30)


GOOD = deploy.Facts(
    branch="main",
    dirty=[],
    head="a" * 40,
    origin_main="a" * 40,
    ci="success",
    slots=DEFAULT,
    timezone="America/New_York",
    state_reads="dict",
    now=ny(30, 12, 0),
)


def failed(facts: object, rollout_step: str | None = None) -> list[str]:
    return [c.name for c in deploy.evaluate(facts, rollout_step) if not c.ok]


def test_all_checks_pass_on_a_clean_green_main() -> None:
    assert failed(GOOD) == []


def test_refuses_off_main_and_says_where() -> None:
    checks = deploy.evaluate(replace(GOOD, branch="x0/tooling"), None)
    branch = next(c for c in checks if c.name == "branch")
    assert not branch.ok
    assert branch.detail == "on x0/tooling"


@pytest.mark.parametrize(
    ("change", "name"),
    [
        ({"dirty": ["src/app.py"]}, "clean tree"),
        ({"origin_main": "b" * 40}, "equal to origin/main"),
        ({"ci": "failure"}, "CI green"),
        ({"ci": "in_progress"}, "CI green"),
        ({"ci": "none"}, "CI green"),
        ({"now": ny(30, 21, 45)}, "outside the blackout"),
        ({"state_reads": "postgres"}, "STATE_READS"),
    ],
)
def test_each_rule_refuses(change: dict[str, object], name: str) -> None:
    assert failed(replace(GOOD, **change)) == [name]


def test_rollout_step_allows_postgres_reads_only() -> None:
    assert failed(replace(GOOD, state_reads="postgres"), "4c.7") == []
    assert failed(replace(GOOD, state_reads="postgres", now=ny(30, 21, 45)), "4c.7") == [
        "outside the blackout"
    ]


def fake_run(stdout: str, code: int = 0) -> object:
    def run(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(list(cmd), code, stdout, "")

    return run


def test_ci_conclusion() -> None:
    assert deploy.ci_conclusion(fake_run("completed\tsuccess\n"), "abc") == "success"
    assert deploy.ci_conclusion(fake_run("completed\tfailure\n"), "abc") == "failure"
    assert deploy.ci_conclusion(fake_run("in_progress\t\n"), "abc") == "in_progress"
    assert deploy.ci_conclusion(fake_run("\n"), "abc") == "none"
    assert deploy.ci_conclusion(fake_run("", 1), "abc").startswith("unknown")


def test_log_line_keeps_the_table_intact() -> None:
    line = deploy.log_line(ny(30, 12, 0), "abcdef123", "deploy-x", "owner", "a | b\nc")
    assert line == "| 2026-09-30 12:00 | abcdef1 | deploy-x | owner | a / b c |\n"


def test_reason_is_required_to_deploy() -> None:
    with pytest.raises(SystemExit):
        deploy.main([])


FULL_ENV = "POSTING_SLOTS=8:00,21:30\nPOSTING_TIMEZONE=America/New_York\nSTATE_READS=dict\n"


def test_env_settings_read_from_the_file(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("API_TOKEN=secret\n" + FULL_ENV)
    env = deploy.read_env_settings(tmp_path / ".env")
    assert env.problems == ()
    assert env.slots == ["08:00", "21:30"]
    assert env.timezone == "America/New_York"
    assert env.state_reads == "dict"


@pytest.mark.parametrize("key", ["POSTING_SLOTS", "POSTING_TIMEZONE", "STATE_READS"])
def test_a_missing_env_key_refuses_and_names_the_line(
    tmp_path: Path, key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(key, "set-in-the-shell-but-ignored")  # only .env counts
    lines = [line for line in FULL_ENV.splitlines() if not line.startswith(f"{key}=")]
    (tmp_path / ".env").write_text("\n".join(lines) + f"\n{key}=\n")
    env = deploy.read_env_settings(tmp_path / ".env")
    assert env.problems == (
        f"{key}= is missing from .env (copy it from clipforge-secrets, identical)",
    )
    facts = replace(
        GOOD,
        slots=env.slots,
        timezone=env.timezone,
        state_reads=env.state_reads,
        env_problems=env.problems,
    )
    checks = {c.name: c for c in deploy.evaluate(facts, None)}
    assert not checks[".env settings"].ok
    assert f"{key}= is missing" in checks[".env settings"].detail
    blocked = "STATE_READS" if key == "STATE_READS" else "outside the blackout"
    assert not checks[blocked].ok
    assert "unknown" in checks[blocked].detail


def test_no_env_file_refuses_every_key(tmp_path: Path) -> None:
    env = deploy.read_env_settings(tmp_path / ".env")
    assert len(env.problems) == 3
    assert env.slots is None and env.state_reads is None


def test_invalid_env_values_refuse(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "POSTING_SLOTS=25:00\nPOSTING_TIMEZONE=America/New_York\nSTATE_READS=sql\n"
    )
    env = deploy.read_env_settings(tmp_path / ".env")
    assert env.slots is None
    assert env.problems == (
        "POSTING_SLOTS in .env: slots must be HH:MM, e.g. 08:00",
        "STATE_READS in .env must be dict or postgres, not 'sql'",
    )
