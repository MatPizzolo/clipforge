"""Parsing /clip, /status, /resume and bare links (spec §5)."""

from __future__ import annotations

from pathlib import Path

import pytest

from clipforge.bot.commands import (
    ClipCommand,
    CommandError,
    HelpCommand,
    JobCommand,
    PostingCommand,
    build_job_input,
    parse_caption,
    parse_text,
)
from clipforge.models import Permission, TelegramTarget
from tests.bot.fakes import make_settings

URL = "https://media.example.com/ep.mp4"
TARGET = TelegramTarget(chat_id=7, reply_to_message_id=3)


def test_clip_with_options_and_quoted_credit() -> None:
    command = parse_text(f'/clip {URL} n=3 len=20-45 lang=es perm=cc_by credit="Jane Doe, CC BY"')
    assert command == ClipCommand(
        URL,
        {"n": "3", "len": "20-45", "lang": "es", "perm": "cc_by", "credit": "Jane Doe, CC BY"},
    )


def test_clip_addressed_to_the_bot() -> None:
    assert parse_text(f"/clip@ClipForgeBot {URL}") == ClipCommand(URL, {})


def test_bare_link_is_a_clip_command() -> None:
    assert parse_text(URL) == ClipCommand(URL, {})
    assert parse_text(f"{URL} n=2") == ClipCommand(URL, {"n": "2"})


def test_status_and_resume() -> None:
    assert parse_text("/status 20260923-aaaaaaaa-0001") == JobCommand(
        "status", "20260923-aaaaaaaa-0001"
    )
    assert parse_text("/resume J") == JobCommand("resume", "J")


@pytest.mark.parametrize("text", ["/start", "/help", "hello there", "", "   "])
def test_everything_else_is_help(text: str) -> None:
    assert parse_text(text) == HelpCommand()


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("/clip", "Usage: /clip"),
        ("/clip not-a-link", "Usage: /clip"),
        (f"/clip {URL} style=bold", "Unknown option"),
        (f"/clip {URL} n=", "Unknown option"),
        (f'/clip {URL} credit="open', "quotes"),
        ("/status a b", "Usage: /status"),
    ],
)
def test_errors_explain_themselves(text: str, fragment: str) -> None:
    with pytest.raises(CommandError, match=fragment):
        parse_text(text)


def test_caption_options() -> None:
    assert parse_caption(None) == {}
    assert parse_caption("n=2 len=10-20") == {"n": "2", "len": "10-20"}
    assert parse_caption("Great talk! Worth a watch") == {}  # a forwarded video's caption
    with pytest.raises(CommandError, match="Unknown option"):
        parse_caption("n=2 style=bold")  # it has options, so a bad one is reported


def test_build_job_input_uses_settings_defaults(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, default_clip_count=4, default_clip_len="25-50")
    job_input = build_job_input(settings, {}, TARGET, url=URL)
    assert str(job_input.source_url) == URL
    assert job_input.permission is Permission.OWN
    assert (job_input.options.n, job_input.options.min_len, job_input.options.max_len) == (
        4,
        25.0,
        50.0,
    )
    assert job_input.notify == TARGET


def test_build_job_input_applies_options(tmp_path: Path) -> None:
    options = {"n": "2", "len": "10-20", "lang": "auto", "perm": "cc_by", "credit": "Jane"}
    job_input = build_job_input(make_settings(tmp_path), options, None, telegram_file_id="F")
    assert job_input.telegram_file_id == "F" and job_input.notify is None
    assert job_input.options.n == 2 and job_input.options.language is None
    assert job_input.permission is Permission.CC_BY and job_input.source_credit == "Jane"


@pytest.mark.parametrize(
    ("options", "fragment"),
    [
        ({"n": "99"}, "options.n"),
        ({"len": "abc"}, "len must look like"),
        ({"len": "60-30"}, "min_len"),
        ({"perm": "cc_by"}, "credit"),
        ({"perm": "stolen"}, "permission"),
    ],
)
def test_build_job_input_errors(tmp_path: Path, options: dict[str, str], fragment: str) -> None:
    with pytest.raises(CommandError, match=fragment):
        build_job_input(make_settings(tmp_path), options, TARGET, url=URL)


def test_build_job_input_is_automatic_by_default(tmp_path: Path) -> None:
    job_input = build_job_input(make_settings(tmp_path), {}, TARGET, url=URL)
    assert job_input.options.n is None and job_input.options.min_score == 0.80


def test_build_job_input_n_auto_and_score(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, default_clip_count=5)
    options = {"n": "auto", "score": "0.85"}
    job_input = build_job_input(settings, options, TARGET, url=URL)
    assert job_input.options.n is None and job_input.options.min_score == 0.85


def test_score_option_parses_and_validates(tmp_path: Path) -> None:
    assert parse_text(f"/clip {URL} score=0.9") == ClipCommand(URL, {"score": "0.9"})
    with pytest.raises(CommandError, match="min_score"):
        build_job_input(make_settings(tmp_path), {"score": "2"}, TARGET, url=URL)


def test_posting_commands() -> None:
    assert parse_text("/status") == PostingCommand("overview")
    assert parse_text("/status 20260928-aaaaaaaa-0001") == JobCommand(
        "status", "20260928-aaaaaaaa-0001"
    )
    assert parse_text("/next") == PostingCommand("next")
    assert parse_text("/pause") == PostingCommand("pause")
    assert parse_text("/go@ClipForgeBot") == PostingCommand("go")


def test_posting_commands_take_an_optional_account() -> None:
    assert parse_text("/pause") == PostingCommand("pause")
    assert parse_text("/pause founder-tapes-en") == PostingCommand("pause", "founder-tapes-en")
    assert parse_text("/next realtalk-clips-en") == PostingCommand("next", "realtalk-clips-en")
    assert parse_text("/go") == PostingCommand("go")
    with pytest.raises(CommandError):
        parse_text("/pause a b")
