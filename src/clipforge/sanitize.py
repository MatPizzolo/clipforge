"""Sanitizers for text that reaches a log line, a chat message or a job's error field.

`clean` is for user-facing text (job errors) and only removes secrets, so file names and
ffmpeg messages stay readable. `redact` describes a driver error for logs and also hides
hosts, addresses and user names."""

from __future__ import annotations

import re

_WEB_QUERY = re.compile(r"(https?://[^\s?#]+)[?#]\S*", re.IGNORECASE)
_OTHER_URL = re.compile(r"\b(?!https?://)[a-z][a-z0-9+.-]*://[^\s'\"<>]+", re.IGNORECASE)
_USERINFO = re.compile(r"\b([a-z][a-z0-9+.-]*://)[^/\s@]+@", re.IGNORECASE)  # any scheme
_BOT_TOKEN = re.compile(r"bot\d+:[A-Za-z0-9_-]+")  # Telegram puts the token in file URL paths
_KV = re.compile(r"\b(password|user|host|dbname)=\S+", re.IGNORECASE)
_HOST = re.compile(r"\S*\.neon\.tech\S*|\bep-[a-z0-9-]+\S*", re.IGNORECASE)
_USER = re.compile(r'\b(user|role) "[^"]*"', re.IGNORECASE)  # psycopg/Postgres quoted user name
_QUOTED = re.compile(r'"[^"\s]*[.:][^"\s]*"')  # a quoted host, address or socket path
_IPV4 = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
_IPV6 = re.compile(r"(?<![\w:])[0-9a-f]{0,4}(?::[0-9a-f]{0,4}){2,7}(?![\w:])", re.IGNORECASE)


def _ipv6(match: re.Match[str]) -> str:
    text = match.group(0)
    # "10:20:30" is a timestamp: an address has "::" or all 8 groups.
    return "<ip>" if "::" in text or text.count(":") == 7 else text


def _secrets(text: str) -> str:
    # URL rules run first: the later rules insert "<redacted>", which would end a URL match.
    text = _WEB_QUERY.sub(r"\1", text)
    text = _USERINFO.sub(r"\1<redacted>@", text)
    text = _BOT_TOKEN.sub("bot<redacted>", text)
    return _KV.sub(r"\1=<redacted>", text)


def _cap(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1] + "\u2026"


def clean(text: str, limit: int = 300) -> str:
    """User-facing text with secrets removed: URL query strings, URL userinfo (any scheme,
    so `postgresql://u:p@h` too), Telegram bot tokens and `key=value` secrets."""
    return _cap(_secrets(text), limit)


def redact(exc: BaseException) -> str:
    """A log- and response-safe description of a driver error: no URL, host, address or
    user name. Non-web URLs (database URLs) are dropped whole."""
    text = (str(exc).splitlines() or [""])[0]
    text = _secrets(_OTHER_URL.sub("<url>", text))
    text = _USER.sub(r"\1 <user>", text)
    text = _QUOTED.sub("<host>", text)
    text = _IPV4.sub("<ip>", text)
    text = _IPV6.sub(_ipv6, text)
    text = _HOST.sub("<host>", text)
    return f"{type(exc).__name__}: {text}"[:200]
