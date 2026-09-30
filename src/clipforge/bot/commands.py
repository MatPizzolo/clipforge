"""Parse bot messages into commands and build a JobInput from options (spec §5).

Pure functions: no Telegram, no Dict. The CLI reuses `build_job_input`, so `/clip` options and
`clipforge run` flags validate the same way.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from typing import Literal

from pydantic import ValidationError

from clipforge.config import Settings
from clipforge.models import JobInput, TelegramTarget

OPTION_KEYS = ("n", "len", "lang", "perm", "credit", "score")
_URL = re.compile(r"https?://\S+", re.IGNORECASE)
_CLIP_USAGE = (
    'Usage: /clip <link> [n=auto] [score=0.8] [len=30-60] [lang=en] [perm=own] [credit="..."]'
)
_OPTIONS_HINT = 'Options: n=auto score=0.8 len=30-60 lang=en perm=own credit="..."'


class CommandError(ValueError):
    """A message the user can fix; `str(exc)` is the reply."""


@dataclass(frozen=True)
class ClipCommand:
    url: str
    options: dict[str, str]


@dataclass(frozen=True)
class JobCommand:
    name: Literal["status", "resume"]
    job_id: str


@dataclass(frozen=True)
class HelpCommand:
    pass


@dataclass(frozen=True)
class PostingCommand:
    name: Literal["overview", "next", "pause", "go"]
    account: str | None = None


Command = ClipCommand | JobCommand | PostingCommand | HelpCommand


def _split(text: str) -> list[str]:
    try:
        return shlex.split(text)
    except ValueError:
        raise CommandError("Unbalanced quotes in the command.") from None


def parse_text(text: str) -> Command:
    tokens = _split(text.strip())
    if not tokens:
        return HelpCommand()
    head = tokens[0]
    if head.startswith("/"):
        name = head.split("@", 1)[0].lower()  # "/clip@ClipForgeBot"
        if name == "/clip":
            if len(tokens) < 2 or not _URL.fullmatch(tokens[1]):
                raise CommandError(_CLIP_USAGE)
            return ClipCommand(tokens[1], parse_options(tokens[2:]))
        if name == "/status":
            if len(tokens) == 1:
                return PostingCommand("overview")
            if len(tokens) == 2:
                return JobCommand("status", tokens[1])
            raise CommandError("Usage: /status [<job_id>]")
        if name == "/resume":
            if len(tokens) != 2:
                raise CommandError("Usage: /resume <job_id>")
            return JobCommand("resume", tokens[1])
        if name in ("/next", "/pause", "/go"):
            if len(tokens) > 2:
                raise CommandError(f"Usage: {name} [<account>]")
            account = tokens[1] if len(tokens) == 2 else None
            return PostingCommand(name[1:], account)  # type: ignore[arg-type]
        return HelpCommand()
    if _URL.fullmatch(head):
        return ClipCommand(head, parse_options(tokens[1:]))
    return HelpCommand()


def parse_options(tokens: list[str]) -> dict[str, str]:
    options: dict[str, str] = {}
    for token in tokens:
        key, sep, value = token.partition("=")
        key = key.lower()
        if not sep or not value or key not in OPTION_KEYS:
            raise CommandError(f"Unknown option {token!r}. {_OPTIONS_HINT}")
        options[key] = value
    return options


def parse_caption(caption: str | None) -> dict[str, str]:
    """Options written in an uploaded video's caption, e.g. `n=2 len=10-20`.

    A caption without any `key=value` token is ordinary text (a forwarded video) and is
    ignored; one with options is parsed strictly, so typos are reported."""
    if not caption or "=" not in caption:
        return {}
    return parse_options(_split(caption))


def build_job_input(
    settings: Settings,
    options: dict[str, str],
    target: TelegramTarget | None,
    *,
    url: str | None = None,
    telegram_file_id: str | None = None,
    source_path: str | None = None,
) -> JobInput:
    low, high = settings.default_clip_len
    clip: dict[str, object] = {
        "n": settings.default_clip_count,
        "min_score": settings.default_min_score,
        "min_len": low,
        "max_len": high,
    }
    if "n" in options:
        clip["n"] = None if options["n"].lower() == "auto" else options["n"]
    if "score" in options:
        clip["min_score"] = options["score"]
    if "len" in options:
        min_len, sep, max_len = options["len"].partition("-")
        if not sep:
            raise CommandError("len must look like 30-60 (seconds).")
        clip["min_len"], clip["max_len"] = min_len, max_len
    if "lang" in options:
        lang = options["lang"]
        clip["language"] = None if lang.lower() == "auto" else lang
    data: dict[str, object] = {
        "source_url": url,
        "telegram_file_id": telegram_file_id,
        "source_path": source_path,
        "permission": options.get("perm", settings.default_permission),
        "source_credit": options.get("credit"),
        "options": clip,
        "notify": target.model_dump() if target is not None else None,
    }
    try:
        return JobInput.model_validate(data)
    except ValidationError as exc:
        raise CommandError(_first_error(exc)) from None


def _first_error(exc: ValidationError) -> str:
    error = exc.errors()[0]
    where = ".".join(str(part) for part in error["loc"])
    message = str(error["msg"]).removeprefix("Value error, ")
    return f"Invalid {where}: {message}" if where else message
