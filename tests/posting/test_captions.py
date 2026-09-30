"""Per-platform caption text (a template until the Phase 3 post.md copy)."""

from __future__ import annotations

from clipforge.posting.captions import instagram, tiktok, youtube_description, youtube_title
from tests.posting.builders import item

TAGS = ["growth", "mindset", "men", "podcast", "honesty", "clips"]


def test_tiktok_has_hook_credit_and_tags() -> None:
    assert tiktok(item(hook="I changed."), TAGS) == (
        "I changed.\n\n🎙️ Billy Garton Jr.\n\n#growth #mindset #men #podcast #honesty #clips"
    )


def test_instagram_title_first_and_at_most_five_tags() -> None:
    text = instagram(item(title="Be honest", hook="Hook."), TAGS)
    assert text.startswith("Be honest\n\nHook.\n\n🎙️ Billy Garton Jr.")
    assert text.endswith("#growth #mindset #men #podcast #honesty")


def test_youtube_title_limits() -> None:
    assert youtube_title(item(title="Real <men> talk")) == "Real men talk #shorts"
    long = youtube_title(item(title="word " * 40))
    assert len(long) == 100 and long.endswith("… #shorts")


def test_long_text_is_cut_to_the_platform_limit() -> None:
    assert len(tiktok(item(hook="x" * 3000), TAGS)) == 2200
    assert len(instagram(item(hook="x" * 3000), TAGS)) == 2200
    assert len(youtube_description(item(hook="x" * 6000), TAGS)) == 5000


def test_links_follow_the_credit() -> None:
    links = ["https://a.example/x", "https://b.example/y"]
    expected = "🎙️ Billy Garton Jr.\n\nhttps://a.example/x\nhttps://b.example/y\n\n#growth"
    assert expected in tiktok(item(), TAGS, links)
    assert expected in youtube_description(item(), TAGS, links)
    assert "🎙️ Billy Garton Jr.\n\nhttps://a.example/x" in instagram(item(), TAGS, links)
    assert tiktok(item(), TAGS) == tiktok(item(), TAGS, ())  # no links: today's text
