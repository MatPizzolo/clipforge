"""Per-platform post text from a clip's title, hook and creator credit.

A template on purpose: LLM-written copy is the Phase 3 `post.md` item and can replace these."""

from __future__ import annotations

from collections.abc import Sequence

from clipforge.models import ContentItem

TIKTOK_MAX = 2200
INSTAGRAM_MAX = 2200
INSTAGRAM_MAX_HASHTAGS = 5
YOUTUBE_TITLE_MAX = 100
YOUTUBE_DESCRIPTION_MAX = 5000
SHORTS_TAG = " #shorts"


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _join(*parts: str) -> str:
    return "\n\n".join(part for part in parts if part)


def _credit(item: ContentItem) -> str:
    return f"🎙️ {item.credits[0]}" if item.credits else ""


def _links(links: Sequence[str]) -> str:
    return "\n".join(links)


def _tags(hashtags: list[str], limit: int | None = None) -> str:
    return " ".join(f"#{tag}" for tag in hashtags[:limit])


def tiktok(item: ContentItem, hashtags: list[str], links: Sequence[str] = ()) -> str:
    return _cut(_join(item.hook, _credit(item), _links(links), _tags(hashtags)), TIKTOK_MAX)


def instagram(item: ContentItem, hashtags: list[str], links: Sequence[str] = ()) -> str:
    tags = _tags(hashtags, INSTAGRAM_MAX_HASHTAGS)
    text = _join(item.title, item.hook, _credit(item), _links(links), tags)
    return _cut(text, INSTAGRAM_MAX)


def youtube_title(item: ContentItem) -> str:
    """YouTube rejects `<` and `>` in titles."""
    title = " ".join(item.title.replace("<", "").replace(">", "").split())
    return _cut(title, YOUTUBE_TITLE_MAX - len(SHORTS_TAG)) + SHORTS_TAG


def youtube_description(item: ContentItem, hashtags: list[str], links: Sequence[str] = ()) -> str:
    text = _join(item.hook, _credit(item), _links(links), _tags(hashtags))
    return _cut(text, YOUTUBE_DESCRIPTION_MAX)
