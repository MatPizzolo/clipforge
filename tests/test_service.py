from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.exc import OperationalError

from clipforge.bot.context import BotContext
from clipforge.db.engine import Database
from clipforge.db.jobs import JobsRepo
from clipforge.jobs import DictJobStore
from clipforge.models import (
    LEGACY_PLATFORMS,
    JobInput,
    JobStatus,
    Permission,
    PostSend,
    PostStatus,
    PostVerdict,
    StageCost,
    StageName,
)
from clipforge.pipeline.deps import MemoryKV, SpawnCall
from clipforge.pipeline.steps import JobNotResumable, fail_job, resume
from clipforge.posting.repo import DictPostingRepo
from clipforge.service import (
    create_job,
    get_job_view,
    job_summaries,
    posting_overview,
    resume_job,
)
from tests.bot.fakes import ALLOWED_USER, make_settings
from tests.bot.helpers import two_account_ctx
from tests.pipeline.fakes import FakeStages
from tests.pipeline.harness import Harness
from tests.posting.builders import ACCOUNT, JOB
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


# ---- card 002 A5: the jobs table first


def _expire(harness: Harness, job_id: str) -> None:
    """The Dict's 7-day expiry (ADR-24) took the job's core record."""
    harness.store.kv.delete(f"job:{job_id}")


def test_job_view_reads_the_jobs_table_first(tmp_path: Path, db: Database) -> None:
    harness = Harness.build(tmp_path)
    harness.deps.jobs_db = JobsRepo(db)
    done = channel_job(harness)
    failed = harness.submit()
    fail_job(harness.deps, failed, StageName.INGEST, "boom", "no audio")
    # both still in the Dict: the row's status, the Dict's clips
    view = get_job_view(harness.store, harness.root, done, harness.deps.jobs_db)
    assert view.status is JobStatus.DONE and view.clips
    assert view.cost.total_usd == pytest.approx(JobsRepo(db).get(done).cost_usd)  # type: ignore[union-attr]
    # expired from the Dict: the row still answers, a failed job too (metadata.json has none)
    _expire(harness, done)
    _expire(harness, failed)
    gone = get_job_view(harness.store, harness.root, done, harness.deps.jobs_db)
    assert gone.status is JobStatus.DONE and gone.clips == [] and gone.cost.stages
    assert gone.output_zip == f"{done}/job.zip"
    lost = get_job_view(harness.store, harness.root, failed, harness.deps.jobs_db)
    assert lost.status is JobStatus.FAILED and lost.output_zip is None
    with pytest.raises(KeyError):  # without the table, the failed job was unknown
        get_job_view(harness.store, harness.root, failed)


def test_a_newer_dict_record_beats_the_row(tmp_path: Path, db: Database) -> None:
    stages = FakeStages(transient=Counter({"highlights": 99}))
    harness = Harness.build(tmp_path, stages)
    harness.deps.jobs_db = JobsRepo(db)
    job_id = harness.submit()
    harness.run()
    assert JobsRepo(db).get(job_id).status is JobStatus.FAILED  # type: ignore[union-attr]
    harness.deps.jobs_db = None  # the resume's row write is lost
    resume(harness.deps, job_id)
    view = get_job_view(harness.store, harness.root, job_id, JobsRepo(db))
    assert view.status is JobStatus.RUNNING


def test_job_view_falls_back_to_the_dict_when_the_table_is_down(harness: Harness) -> None:
    class Down:
        def get(self, job_id: str) -> None:
            raise OperationalError("SELECT", {}, Exception("neon asleep"))

    job_id = harness.submit()
    harness.run()
    view = get_job_view(harness.store, harness.root, job_id, Down())  # type: ignore[arg-type]
    assert view.status is JobStatus.DONE and len(view.clips) == 5


def test_job_summaries_are_the_table_plus_dict_jobs_it_lacks(tmp_path: Path, db: Database) -> None:
    harness = Harness.build(tmp_path)
    harness.deps.jobs_db = JobsRepo(db)
    in_table = channel_job(harness)
    harness.deps.jobs_db = None
    only_dict = harness.submit()  # its row write never happened (before the backfill)
    harness.deps.jobs_db = JobsRepo(db)
    _expire(harness, in_table)
    assert [s.job_id for s in job_summaries(harness.deps)] == sorted([in_table, only_dict])

    class Down:
        def list(self) -> None:
            raise OperationalError("SELECT", {}, Exception("neon asleep"))

    harness.deps.jobs_db = Down()  # type: ignore[assignment]
    assert [s.job_id for s in job_summaries(harness.deps)] == [only_dict]


def test_overview_state_posted_total_unanswered_and_last_send(tmp_path: Path, db: Database) -> None:
    ctx = two_account_ctx(tmp_path, db)
    posting = ctx.deps.posting
    assert posting is not None
    noon = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
    view = posting_overview(ctx.deps, ctx.settings, noon)
    assert (view.state, view.posted_total) == ("on", 0)
    assert view.accounts[1].unanswered == 0 and view.accounts[1].last_sent_at is None

    ref = f"{JOB}:clip_01"
    sent_at = datetime(2026, 9, 29, 12, 1, tzinfo=UTC)
    posting.repo.add_send(
        ref, PostSend(n=1, at=sent_at, slot=None, message_id=5, video_message_id=4), ALLOWED_USER
    )
    realtalk = posting_overview(ctx.deps, ctx.settings, noon).accounts[1]
    assert (realtalk.unanswered, realtalk.last_sent_at, realtalk.state) == (1, sent_at, "on")

    for platform in LEGACY_PLATFORMS:
        posting.repo.set_posted(ref, platform, True, sent_at)
    posting.repo.set_paused("founder-tapes-en", True, sent_at)
    view = posting_overview(ctx.deps, ctx.settings, noon)
    founder, realtalk = view.accounts
    assert (view.posted_total, realtalk.posted_total, realtalk.unanswered) == (1, 1, 0)
    assert (founder.state, realtalk.state, view.state) == ("paused", "on", "on")


def test_overview_state_waiting_off_and_problem(harness: Harness) -> None:
    channel_job(harness)
    store = DictPostingRepo(harness.store.kv, ACCOUNT)
    at = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
    first, second, _ = sorted(store.records(ACCOUNT), key=lambda r: r.item.id)
    for n, record in enumerate((first, second), start=1):
        store.add_send(
            record.item.id, PostSend(n=1, at=at, slot=None, message_id=n, video_message_id=n)
        )
    on = make_settings(harness.root, posting_chat_id=ALLOWED_USER)
    assert posting_overview(harness.deps, on, at).state == "waiting"  # the pause rule holds
    assert posting_overview(harness.deps, make_settings(harness.root), at).state == "off"
    broken = make_settings(harness.root, posting_chat_id=ALLOWED_USER, posting_slots="9am")
    assert posting_overview(harness.deps, broken, at).state == "problem"


def test_job_summaries_take_a_newer_dict_record_over_its_row(tmp_path: Path, db: Database) -> None:
    # migration review I3 / PR review 9: the same "newer wins" rule as get_job_view
    stages = FakeStages(transient=Counter({"highlights": 99}))
    harness = Harness.build(tmp_path, stages)
    harness.deps.jobs_db = JobsRepo(db)
    job_id = harness.submit()
    harness.run()  # failed, and its row says so
    harness.deps.jobs_db = None
    resume(harness.deps, job_id)  # the resume's row write is lost
    harness.deps.jobs_db = JobsRepo(db)
    [summary] = job_summaries(harness.deps)
    assert summary.status is JobStatus.RUNNING


def test_a_row_without_cost_rows_takes_the_breakdown_from_metadata(
    tmp_path: Path, db: Database
) -> None:
    # pipeline review I1: never a made-up PACKAGE line (the dashboard sums costs per stage)
    # Flaky on WSL2 (card 017): when the wall clock steps back between create_job and package,
    # JobsRepo.upsert's `updated_at <=` guard silently drops the DONE write and the row stays
    # `queued`. A src/ bug, not a test bug: root cause and the fix in docs/reports/017-x0-*.md
    harness = Harness.build(tmp_path)
    harness.deps.jobs_db = JobsRepo(db)
    job_id = channel_job(harness)
    JobsRepo(db).replace_costs(job_id, [])  # a backfill that wrote no per-stage rows
    _expire(harness, job_id)
    row = JobsRepo(db).get(job_id)
    assert row is not None and row.metadata_path is not None
    path = tmp_path / row.metadata_path
    meta = JobMetadata.model_validate_json(path.read_text())
    stages = [StageCost(stage=StageName.TRANSCRIBE, gpu_s=9.0, usd_estimate=0.002),
              StageCost(stage=StageName.HIGHLIGHTS, usd_estimate=0.0015)]  # fmt: skip
    meta = meta.model_copy(update={"cost": meta.cost.model_copy(update={"stages": stages})})
    path.write_text(meta.model_dump_json())  # the real pipeline writes a full breakdown
    view = get_job_view(harness.store, harness.root, job_id, harness.deps.jobs_db)
    assert view.cost.stages == stages
    assert all(c.stage is not StageName.PACKAGE for c in view.cost.stages)


def test_restore_clears_the_outage_and_status_shows_it(harness: Harness) -> None:
    from clipforge.bot.messages import posting_overview_text
    from clipforge.posting.keepalive import OUTAGE_KEY, outage_since
    from clipforge.service import restore_posting

    channel_job(harness)
    harness.store.kv.put(OUTAGE_KEY, "2026-09-25")
    settings = make_settings(harness.root, posting_chat_id=ALLOWED_USER)
    at = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
    view = posting_overview(harness.deps, settings, at)
    assert (view.state, view.outage_since) == ("outage", "2026-09-25")
    assert "posting_daily didn't run since 2026-09-25" in posting_overview_text(view)
    restore_posting(harness.deps)
    assert outage_since(harness.store.kv) is None
    assert posting_overview(harness.deps, settings, at).state == "on"


# ---- card 039: the overview's reads don't grow with the number of jobs and clips


def _overview_selects(ctx: BotContext, db: Database, extra: int) -> int:
    from sqlalchemy import event

    from clipforge.models import ChannelRef, Job
    from clipforge.pipeline.steps import summary_of
    from tests.posting.builders import item

    assert ctx.deps.posting is not None
    ctx.deps.jobs_db = JobsRepo(db)
    t0 = datetime(2026, 9, 28, tzinfo=UTC)
    for n in range(extra):
        job_id = f"20260928-cccccccc-{n:04d}"
        channel = ChannelRef(slug="billy-garton", name="Billy Garton Jr.")
        job_input = JobInput(source_url="https://example.com/v.mp4", source_label=f"ep{n}",
                             permission=Permission.CREATOR_AGREEMENT, channel=channel)  # fmt: skip
        job = Job(job_id=job_id, status=JobStatus.DONE, input=job_input, created_at=t0,
                  updated_at=t0)  # fmt: skip
        ctx.deps.jobs_db.upsert(summary_of(job))
        ctx.deps.posting.repo.add(item(job_id=job_id, source_hash=f"{n:064d}"),
                                  list(LEGACY_PLATFORMS))  # fmt: skip
    statements: list[str] = []

    def capture(conn: object, cursor: object, sql: str, *rest: object) -> None:
        statements.append(sql)

    event.listen(db.engine, "before_cursor_execute", capture)
    try:
        view = posting_overview(ctx.deps, ctx.settings, datetime(2026, 9, 29, 12, tzinfo=UTC))
    finally:
        event.remove(db.engine, "before_cursor_execute", capture)
    assert view.accounts[1].waiting == 1 + extra
    return sum(s.lstrip().upper().startswith("SELECT") for s in statements)


def test_the_overview_reads_a_constant_number_of_queries(tmp_path: Path, db: Database) -> None:
    from sqlalchemy import text

    from clipforge.db.tables import metadata

    few = _overview_selects(two_account_ctx(tmp_path / "a", db), db, 1)
    names = ", ".join(table.name for table in reversed(metadata.sorted_tables))
    with db.begin() as conn:  # the same database for the second count
        conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    many = _overview_selects(two_account_ctx(tmp_path / "b", db), db, 8)
    assert many == few, (few, many)


def test_job_summaries_read_the_dict_once(harness: Harness) -> None:
    # card 039: one streaming read of the Dict, not one `get` per job
    channel_job(harness)
    channel_job(harness)
    kv = harness.store.kv
    gets: list[str] = []
    real_get = kv.get

    def counting_get(key: str) -> str | None:
        gets.append(key)
        return real_get(key)

    kv.get = counting_get  # type: ignore[method-assign]
    assert len(job_summaries(harness.deps)) == 2
    assert [k for k in gets if k.startswith("job:")] == []
