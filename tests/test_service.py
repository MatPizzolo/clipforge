from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from clipforge.db.engine import Database
from clipforge.jobs import DictJobStore
from clipforge.models import (
    LEGACY_PLATFORMS,
    JobInput,
    JobStatus,
    Permission,
    PostStatus,
    PostVerdict,
    StageName,
)
from clipforge.pipeline.deps import MemoryKV, SpawnCall
from clipforge.pipeline.steps import JobNotResumable
from clipforge.posting.repo import DictPostingRepo
from clipforge.service import create_job, get_job_view, posting_overview, resume_job
from tests.bot.fakes import ALLOWED_USER, make_settings
from tests.bot.helpers import two_account_ctx
from tests.pipeline.fakes import FakeStages
from tests.pipeline.harness import Harness
from tests.posting.builders import ACCOUNT
from tests.posting.builders import run_channel_job as channel_job
from tests.test_models import ALL_SAMPLES, JobMetadata


def test_create_job_saves_and_spawns_ingest(harness: Harness) -> None:
    job_input = JobInput(telegram_file_id="BQACAgIAAxk", permission=Permission.OWN)
    job = create_job(harness.deps, job_input)
    assert harness.store.get(job.job_id) == job
    assert job.status is JobStatus.QUEUED
    assert list(harness.spawner.queue) == [SpawnCall("ingest", job.job_id, None)]


def test_job_view_merges_clip_costs(harness: Harness) -> None:
    job_id = harness.submit()
    harness.run()
    view = get_job_view(harness.store, harness.root, job_id)
    assert view.status is JobStatus.DONE and len(view.clips) == 5
    renders = [c for c in view.cost.stages if c.stage is StageName.RENDER and not c.cached]
    assert len(renders) == 5 and all(c.clip_id for c in renders)
    # fake costs: transcribe 0.002 + highlights 0.0015 + 5 clips x 0.001
    assert view.cost.total_usd == pytest.approx(0.0085)
    assert view.output_zip is not None


def test_job_view_falls_back_to_metadata(tmp_path: Path) -> None:
    meta = next(m for m in ALL_SAMPLES if isinstance(m, JobMetadata))
    path = tmp_path / meta.job_id / "output" / "metadata.json"
    path.parent.mkdir(parents=True)
    path.write_text(meta.model_dump_json())
    store = DictJobStore(MemoryKV())  # Dict entries are gone
    view = get_job_view(store, tmp_path, meta.job_id)
    assert view.status is JobStatus.DONE and view.cost == meta.cost
    assert view.output_zip == f"{meta.job_id}/job.zip"
    with pytest.raises(KeyError):
        get_job_view(store, tmp_path, "20260923-00000000-0000")


def test_resume_job_returns_the_view(tmp_path: Path) -> None:
    stages = FakeStages(transient=Counter({"highlights": 99}))
    h = Harness.build(tmp_path, stages)
    job_id = h.submit()
    h.run()
    stages.transient.clear()
    view = resume_job(h.deps, job_id)
    assert view.status is JobStatus.RUNNING and view.error is None
    h.run()
    assert get_job_view(h.store, h.root, job_id).status is JobStatus.DONE
    with pytest.raises(JobNotResumable):
        resume_job(h.deps, h.submit())


def test_posting_overview_counts(harness: Harness) -> None:
    channel_job(harness)
    store = DictPostingRepo(harness.store.kv, ACCOUNT)
    first, second, _third = sorted(store.records(ACCOUNT), key=lambda r: r.item.id)
    at = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
    for platform in LEGACY_PLATFORMS:
        store.toggle_posted(first.item.id, platform, at)
    store.set_verdict(second.item.id, PostVerdict(kind="rejected", at=at))
    settings = make_settings(harness.root, posting_chat_id=ALLOWED_USER)
    view = posting_overview(harness.deps, settings, at)
    [channel] = view.channels
    assert channel.slug == "billy-garton"
    assert (channel.episodes_clipped, channel.episodes_failed) == (1, 0)
    assert channel.counts[PostStatus.POSTED] == 1
    assert channel.counts[PostStatus.REJECTED] == 1
    assert channel.counts[PostStatus.QUEUED] == 1
    assert (view.enabled, view.paused, view.waiting, view.per_day, view.days_left) == (
        True, False, 1, 6, 1
    )  # fmt: skip
    assert view.next_slot is not None and view.next_slot > at
    off = posting_overview(harness.deps, make_settings(harness.root), at + timedelta(days=1))
    assert off.enabled is False


def test_posting_overview_reports_the_config_problem(harness: Harness) -> None:
    settings = make_settings(harness.root, posting_chat_id=ALLOWED_USER, posting_slots="9am")
    view = posting_overview(harness.deps, settings, datetime(2026, 9, 29, tzinfo=UTC))
    assert view.enabled is False and view.problem is not None and "HH:MM" in view.problem


def test_overview_has_every_account_and_keeps_top_level_fields(
    tmp_path: Path, db: Database
) -> None:
    ctx = two_account_ctx(tmp_path, db)
    view = posting_overview(ctx.deps, ctx.settings, datetime(2026, 9, 29, 12, 0, tzinfo=UTC))
    assert [a.account_id for a in view.accounts] == ["founder-tapes-en", "realtalk-clips-en"]
    realtalk = view.accounts[1]
    assert view.waiting == realtalk.waiting == 1 and view.per_day == realtalk.per_day == 1
    assert view.enabled is True and view.channels == realtalk.channels
    assert realtalk.timezone == "America/New_York"
