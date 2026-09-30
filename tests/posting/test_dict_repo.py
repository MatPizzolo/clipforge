"""DictPostingRepo specifics: the plan C key format and tolerance of bad values."""

from __future__ import annotations

from clipforge.models import LEGACY_PLATFORMS, ChannelRef, PostItem
from clipforge.pipeline.deps import MemoryKV
from clipforge.posting.repo import DictPostingRepo, to_content_item, to_post_item
from tests.posting.builders import ACCOUNT, T0, item

PLATFORMS = list(LEGACY_PLATFORMS)


def test_invalid_values_are_ignored_not_fatal() -> None:
    kv = MemoryKV()
    repo = DictPostingRepo(kv, ACCOUNT)
    good, bad = item("clip_01"), item("clip_02")
    repo.add(good, PLATFORMS)
    kv.put(f"post:{bad.id}", "not json")  # a bad item is left out
    kv.put(f"post:{good.id}:sent:1", "{}")  # a bad side key is treated as missing
    [rec] = repo.records(ACCOUNT)
    assert rec.item == good and rec.sends == []


def test_items_are_stored_in_the_plan_c_format() -> None:
    """Already-queued clips keep reading: `post:<ref>` holds the legacy PostItem JSON."""
    kv = MemoryKV()
    it = item()
    DictPostingRepo(kv, ACCOUNT).add(it, PLATFORMS)
    legacy = PostItem.model_validate_json(kv.get(f"post:{it.id}") or "")
    billy = ChannelRef(slug="billy-garton", name="Billy Garton Jr.")
    assert legacy.ref == it.id and legacy.channel == billy
    assert to_content_item(legacy, ACCOUNT) == it and to_post_item(it) == legacy


def test_add_refuses_another_accounts_item() -> None:
    kv = MemoryKV()
    assert DictPostingRepo(kv, ACCOUNT).add(item(account="founder-tapes-en"), PLATFORMS) is False
    assert kv.get(f"post:{item().id}") is None


GOLDEN_POST_ITEM = (
    '{"job_id":"20260928-aaaaaaaa-0001","clip_id":"clip_01",'
    '"channel":{"slug":"billy-garton","name":"Billy Garton Jr."},'
    '"source_hash":"' + "a" * 64 + '","start":0.0,"end":30.0,"score":0.85,'
    '"title":"A title","hook":"A hook.","video_path":"cache/clip/clip_01/clip.mp4",'
    '"episode":"ep01","episode_finished_at":"2026-09-28T12:00:00Z",'
    '"queued_at":"2026-09-28T12:00:00Z"}'
)


def test_golden_plan_c_bytes_keep_rollback_possible() -> None:
    """A later change must not alter what plan C code would read back from the Dict."""
    kv = MemoryKV()
    repo = DictPostingRepo(kv, ACCOUNT)
    it = item()
    repo.add(it, PLATFORMS)
    assert kv.get(f"post:{it.id}") == GOLDEN_POST_ITEM
    repo.set_paused(ACCOUNT, True, T0)
    assert kv.get("posting:paused") == "1"
