"""Enqueue: a finished channel job's clips become ContentItems, without duplicate moments."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from clipforge.db.accounts import AccountsRepo
from clipforge.db.engine import Database
from clipforge.models import (
    LEGACY_PLATFORMS,
    CampaignRules,
    ChannelRef,
    Job,
    JobInput,
    Platform,
    PostRecord,
    Source,
    SourcePermission,
)
from clipforge.pipeline.deps import MemoryKV
from clipforge.posting.backend import Posting, build_posting, dict_posting
from clipforge.posting.enqueue import ClipFacts, enqueue, enqueue_job, items_for, platforms_for
from clipforge.posting.repo import DictPostingRepo
from tests.bot.fakes import make_settings
from tests.dbhelpers import BILLY_SOURCE, make_account, seed
from tests.posting.builders import ACCOUNT, T0, item, record

PLATFORMS = list(LEGACY_PLATFORMS)


def _job(channel: str = "billy-garton") -> Job:
    job_input = JobInput(source_url="https://example.com/v.mp4", permission="creator_agreement",
                         channel=ChannelRef(slug=channel, name="Billy"),
                         source_label="ep01")  # fmt: skip
    return Job(job_id="20260928-aaaaaaaa-0001", input=job_input, created_at=T0, updated_at=T0)


def _facts() -> ClipFacts:
    return ClipFacts("clip_01", 1, "a" * 64, 0.0, 30.0, 0.9, "t", "h", "x/clip.mp4")


def test_enqueue_skips_overlapping_moments() -> None:
    store = DictPostingRepo(MemoryKV(), ACCOUNT)
    first = [item("clip_01", start=0, end=30), item("clip_02", start=100, end=130)]
    assert enqueue(store, first, PLATFORMS) == 2
    recut = [
        item("clip_01", job_id="20260929-aaaaaaaa-0002", start=1, end=31),  # same moment
        item("clip_02", job_id="20260929-aaaaaaaa-0002", start=200, end=230),  # new moment
    ]
    assert enqueue(store, recut, PLATFORMS) == 1
    assert enqueue(store, recut, PLATFORMS) == 0  # idempotent
    assert len(store.records(ACCOUNT)) == 3


def test_recut_brings_back_a_moment_whose_video_went_missing() -> None:
    store = DictPostingRepo(MemoryKV(), ACCOUNT)
    gone = item("clip_01", start=0, end=30)
    store.add(gone, list(LEGACY_PLATFORMS))
    store.mark_unavailable(gone.id, T0)
    recut = item("clip_01", job_id="20260929-aaaaaaaa-0002", start=1, end=31)
    assert enqueue(store, [recut], PLATFORMS) == 1


def test_overlap_ignores_unavailable_records() -> None:
    from clipforge.posting.queue import overlaps

    missing: PostRecord = record(item(start=0, end=30), unavailable=True)
    assert not overlaps(item("clip_09", job_id="20260929-aaaaaaaa-0002"), [missing])


def test_items_take_account_credit_license_and_sponsorship_from_the_source(tmp_path: Path) -> None:
    account = make_account("founder-tapes-en", platforms=[Platform.TIKTOK, Platform.YOUTUBE])
    source = Source(id="whop-x", account_id=account.id, credit_name="Whop X", kind="campaign",
                    permission=SourcePermission(type="clipping_program"),
                    campaign=CampaignRules(required_tags=["whop"]))  # fmt: skip
    job = _job(channel="whop-x")
    [it] = items_for(job, [_facts()], T0, account, source, "sha123")
    assert it.account_id == "founder-tapes-en" and it.credits == ["Whop X"]
    assert it.sponsored is True and it.producer_version == "sha123"
    assert it.assets[0].license == "clipping_program" and it.language == "en"
    assert platforms_for(account) == [Platform.TIKTOK, Platform.YOUTUBE]


def test_postgres_mode_needs_a_source_row(tmp_path: Path) -> None:
    posting = dict_posting(MemoryKV(), make_account())
    strict = dataclasses.replace(posting, requires_source=True)
    assert enqueue_job(strict, _job(), [_facts()], T0, "v") == 0  # skipped, logged
    assert enqueue_job(posting, _job(), [_facts()], T0, "v") == 1  # dict mode: account #1


def _posting_with(source: Source, posting: Posting | None = None) -> Posting:
    posting = posting or dict_posting(MemoryKV(), make_account())
    return dataclasses.replace(posting, source=lambda _id: source, requires_source=True)


def test_enqueue_skips_held_sources(caplog: pytest.LogCaptureFixture) -> None:
    expired = BILLY_SOURCE.model_copy(update={"permission": BILLY_SOURCE.permission.model_copy(
        update={"expires_at": T0})})  # fmt: skip
    assert enqueue_job(_posting_with(expired), _job(), [_facts()], T0, "v") == 0
    assert "permission expired 2026-09-28" in caplog.text
    paused = BILLY_SOURCE.model_copy(update={"status": "paused"})
    assert enqueue_job(_posting_with(paused), _job(), [_facts()], T0, "v") == 0
    assert enqueue_job(_posting_with(BILLY_SOURCE), _job(), [_facts()], T0, "v") == 1


def test_enqueue_queues_only_covered_platforms(
    tmp_path: Path, db: Database, caplog: pytest.LogCaptureFixture
) -> None:
    narrow = BILLY_SOURCE.model_copy(update={"permission": SourcePermission(
        type="creator_agreement", platforms=[Platform.TIKTOK])})  # fmt: skip
    seed(db, make_account(), sources=[narrow])
    posting = build_posting(make_settings(tmp_path, state_reads="postgres"), MemoryKV(), db)
    assert enqueue_job(posting, _job(), [_facts()], T0, "v") == 1
    [rec] = posting.repo.records("realtalk-clips-en")
    assert rec.platforms == [Platform.TIKTOK] and "doesn't cover" in caplog.text
    none_left = BILLY_SOURCE.model_copy(update={"permission": SourcePermission(
        type="creator_agreement", platforms=[Platform.FACEBOOK])})  # fmt: skip
    assert enqueue_job(_posting_with(none_left), _job(), [_facts()], T0, "v") == 0


def test_item_platforms_are_frozen_when_the_account_changes(tmp_path: Path, db: Database) -> None:
    # card 002 A3: platforms = the account's enabled platforms ∩ the permission, fixed per item
    account = make_account(platforms=[Platform.TIKTOK, Platform.YOUTUBE])
    seed(db, account, sources=[BILLY_SOURCE])
    posting = build_posting(make_settings(tmp_path, state_reads="postgres"), MemoryKV(), db)
    assert enqueue_job(posting, _job(), [_facts()], T0, "v") == 1
    AccountsRepo(db).update(make_account(platforms=list(Platform)), T0)  # Facebook and IG on
    [rec] = posting.repo.records(account.id)
    assert rec.platforms == [Platform.TIKTOK, Platform.YOUTUBE]
    again = posting.repo.get(rec.item.id)
    assert again is not None and again.platforms == [Platform.TIKTOK, Platform.YOUTUBE]


# ---- the hook stamp (ADR-50, HK-1: HOOK_VARIANTS off)


def test_flag_off_stamps_the_control_with_the_jobs_weights() -> None:
    from tests.hooks.builders import entry, rotation

    rot = rotation(entry("hp_ctl", 1.0, control=True), entry("hp_a", 2.0))
    facts = dataclasses.replace(_facts(), title="Highlight title")
    [it] = items_for(_job(), [facts], T0, make_account(), BILLY_SOURCE, "clips:x", rotation=rot,
                     flag_on=False)  # fmt: skip
    assert it.hook_stamp is not None and it.title == "Highlight title"
    assert it.hook_stamp.result.pattern_id == "hp_ctl" and it.hook_stamp.result.drawn is False
    assert it.hook_stamp.result.text == "Highlight title"
    assert it.hook_stamp.weights == {"hp_ctl@1": 1.0, "hp_a@1": 2.0}
    assert it.hook_stamp.rotation_id == rot.id
    assert it.hook == "h"  # highlights' spoken line is untouched


def test_flag_off_ignores_a_drawn_result() -> None:
    from clipforge.models import HookResult
    from tests.hooks.builders import entry, rotation

    rot = rotation(entry("hp_ctl", 1.0, control=True), entry("hp_a", 2.0))
    drawn = HookResult(pattern_id="hp_a", version=1, variants=["Why?"], chosen=0, text="Why?",
                       drawn=True)  # fmt: skip
    facts = dataclasses.replace(_facts(), hook_result=drawn)
    [off] = items_for(_job(), [facts], T0, make_account(), BILLY_SOURCE, "v", rotation=rot)
    assert off.hook_stamp is not None and off.hook_stamp.result.pattern_id == "hp_ctl"
    assert off.title == "t"
    [on] = items_for(_job(), [facts], T0, make_account(), BILLY_SOURCE, "v", rotation=rot,
                     flag_on=True)  # fmt: skip
    assert on.hook_stamp is not None and on.hook_stamp.result == drawn and on.title == "Why?"


def test_no_rotation_no_stamp() -> None:
    [it] = items_for(_job(), [_facts()], T0, make_account(), BILLY_SOURCE, "v", rotation=None)
    assert it.hook_stamp is None
