"""The chain queues a channel job's clips for posting, and never fails because of it."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

from clipforge.db.engine import Database
from clipforge.db.jobs import JobsRepo
from clipforge.jobs import utcnow
from clipforge.models import ContentItem, Job, JobInput, JobStatus, Platform
from clipforge.posting import keepalive
from clipforge.posting.backend import build_posting
from clipforge.posting.repo import DictPostingRepo
from clipforge.service import PostingOutage, create_job, rebuild_posting
from tests.bot.fakes import make_settings
from tests.dbhelpers import BILLY_SOURCE, make_account, seed
from tests.pipeline.harness import Harness
from tests.posting.builders import ACCOUNT, BILLY, T0
from tests.posting.builders import run_channel_job as channel_job


def test_channel_job_clips_are_queued(harness: Harness) -> None:
    job_id = channel_job(harness)
    records = DictPostingRepo(harness.store.kv, ACCOUNT).records(ACCOUNT)
    assert len(records) == 3
    assert {r.item.clip.job_id for r in records if r.item.clip} == {job_id}
    assert all(r.item.source_id == BILLY.slug and r.item.credits == [BILLY.name] for r in records)
    assert all(r.item.clip and r.item.clip.episode == "ep01" for r in records)
    assert all(r.item.account_id == ACCOUNT for r in records)
    assert all((harness.root / str(r.item.video_path)).is_file() for r in records)


def test_job_without_channel_is_not_queued(harness: Harness) -> None:
    channel_job(harness, channel=None)
    assert DictPostingRepo(harness.store.kv, ACCOUNT).records(ACCOUNT) == []


def test_enqueue_failure_never_fails_the_job(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*args: object, **kwargs: object) -> int:
        raise RuntimeError("dict exploded")

    monkeypatch.setattr("clipforge.pipeline.steps.enqueue_job", boom)
    job_id = channel_job(harness)
    assert harness.store.get(job_id).status is JobStatus.DONE
    assert "done" in harness.event_kinds()


def test_rebuild_queues_old_channel_jobs_once(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("clipforge.pipeline.steps.enqueue_job", lambda *a, **k: 0)  # "old" job
    channel_job(harness)
    monkeypatch.undo()
    assert DictPostingRepo(harness.store.kv, ACCOUNT).records(ACCOUNT) == []
    assert rebuild_posting(harness.deps, utcnow()) == 3
    assert rebuild_posting(harness.deps, utcnow()) == 0


def test_rebuild_refuses_during_an_outage(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A manual rebuild respects the outage flag, like posting_daily does (#217, card 010)."""
    monkeypatch.setattr("clipforge.pipeline.steps.enqueue_job", lambda *a, **k: 0)  # "old" job
    channel_job(harness)
    monkeypatch.undo()
    keepalive.set_outage(harness.store.kv, "2026-09-20")
    with pytest.raises(PostingOutage) as raised:
        rebuild_posting(harness.deps, utcnow())
    assert "2026-09-20" in str(raised.value)
    assert "clipforge status --restore 2026-09-20" in str(raised.value)
    assert DictPostingRepo(harness.store.kv, ACCOUNT).records(ACCOUNT) == []  # nothing queued
    keepalive.clear_outage(harness.store.kv)  # /go or a restore
    assert rebuild_posting(harness.deps, utcnow()) == 3


# ---- Plan B review fixes


def test_crash_right_after_done_still_queues(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The container dies just after the job is saved as done: the retry sees DONE and returns,
    so the clips must already be queued by then."""
    real_save = harness.store.save
    crashed: list[bool] = []

    def save_then_die(job: Job) -> None:
        real_save(job)
        if job.status is JobStatus.DONE and not crashed:
            crashed.append(True)
            raise RuntimeError("container preempted")

    monkeypatch.setattr(harness.store, "save", save_then_die)
    channel_job(harness)
    assert crashed and len(DictPostingRepo(harness.store.kv, ACCOUNT).records(ACCOUNT)) == 3


def test_rebuild_skips_a_broken_job_and_continues(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("clipforge.pipeline.steps.enqueue_job", lambda *a, **k: 0)
    broken = channel_job(harness)  # listed first
    other = run_channel_job_for(harness, "ep02", "https://media.example.com/other.mp4")
    monkeypatch.undo()
    (harness.root / broken / "output" / "metadata.json").unlink()  # e.g. the Volume was cleaned
    assert rebuild_posting(harness.deps, utcnow()) == 3
    assert {
        r.item.id.split(":")[0] for r in DictPostingRepo(harness.store.kv, ACCOUNT).records(ACCOUNT)
    } == {other}


def run_channel_job_for(harness: Harness, label: str, url: str) -> str:
    job_input = JobInput.model_validate(
        {"source_url": url, "permission": "creator_agreement", "options": {"n": 3},
         "source_label": label, "channel": BILLY.model_dump()}
    )  # fmt: skip
    job_id = create_job(harness.deps, job_input).job_id
    harness.run()
    return job_id


def test_the_chain_passes_the_deploy_version_to_enqueue(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[object] = []
    monkeypatch.setattr(
        "clipforge.pipeline.steps.enqueue_job", lambda *a, **k: seen.append(a[-1]) or 0
    )
    harness.deps.version = "abc123"
    channel_job(harness)
    assert seen == ["abc123"]


def test_enqueued_items_carry_the_deploy_version(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert harness.deps.posting is not None
    repo = harness.deps.posting.repo
    added: list[str] = []
    real = repo.add

    def spy(item: ContentItem, platforms: list[Platform]) -> bool:
        added.append(item.producer_version)
        return real(item, platforms)

    monkeypatch.setattr(repo, "add", spy)
    harness.deps.version = "abc123"
    channel_job(harness)
    assert added == ["abc123"] * 3


def test_rebuild_reads_jobs_table_and_metadata_even_after_dict_keys_expire(
    tmp_path: Path, db: Database
) -> None:
    seed(db, make_account(), sources=[BILLY_SOURCE])
    harness = Harness.build(tmp_path)
    harness.deps.jobs_db = JobsRepo(db)
    harness.deps.posting = build_posting(
        make_settings(tmp_path, state_reads="postgres"), harness.store.kv, db
    )
    run_id = channel_job(harness)
    assert run_id
    queued = len(harness.deps.posting.repo.records("realtalk-clips-en"))
    assert queued == 3
    job_keys = [k for k in harness.store.kv.keys() if k.startswith("job:")]  # noqa: SIM118
    for key in job_keys:
        harness.store.kv.delete(key)  # the Dict's 7-day expiry
    assert rebuild_posting(harness.deps, T0) == 0  # idempotent: nothing new
    with db.begin() as conn:
        conn.execute(
            text(
                "delete from posts; delete from post_events; delete from sends; "
                "delete from assets; delete from content_items"
            )
        )
    assert rebuild_posting(harness.deps, T0) == 3  # back from jobs + metadata.json
