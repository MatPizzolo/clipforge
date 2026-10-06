"""Per-platform post text from a clip's title, hook and creator credit.

A template on purpose: LLM-written copy is the Phase 3 `post.md` item and can replace these."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from clipforge.models import Account, ContentItem, Platform, PostCopy, Source

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


def extras(
    account: Account, source: Source | None, item: ContentItem
) -> tuple[list[str], list[str]]:
    """Hashtags and links for one post: #ad first when sponsored, then a campaign's required
    tags, then the account's own (spec §6.3)."""
    tags = list(account.posting.hashtags)
    links: list[str] = []
    if source is not None and source.campaign is not None:
        required = source.campaign.required_tags
        tags = [*required, *(t for t in tags if t not in required)]
        links = [str(link) for link in source.campaign.required_links]
    if item.sponsored:
        tags = ["ad", *(t for t in tags if t != "ad")]
    return tags, links


def copy_for(
    item: ContentItem, account: Account, source: Source | None, platforms: Iterable[Platform]
) -> dict[Platform, PostCopy]:
    """Per-platform copy (S2 spec §2), first version (card 014 Task 7): today's caption texts as
    `PostCopy`, the same text the posting card shows; Facebook gets the TikTok caption. S2b
    (plan Task 13) adds Facebook's own copy, the item's `post_copy` override and tracked links."""
    tags, links = extras(account, source, item)
    out: dict[Platform, PostCopy] = {}
    for p in platforms:
        if p is Platform.INSTAGRAM:
            out[p] = PostCopy(text=instagram(item, tags, links),
                              hashtags=tags[:INSTAGRAM_MAX_HASHTAGS], links=links)  # fmt: skip
        elif p is Platform.YOUTUBE:
            out[p] = PostCopy(title=youtube_title(item),
                              text=youtube_description(item, tags, links), hashtags=tags,
                              links=links)  # fmt: skip
        else:  # TikTok, and Facebook until its own copy (S2b)
            out[p] = PostCopy(text=tiktok(item, tags, links), hashtags=tags, links=links)
    return out
