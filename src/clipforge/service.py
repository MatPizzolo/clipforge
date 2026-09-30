"""Job service: the one entry point shared by the API, the bot and the CLI (ADR-2)."""

from __future__ import annotations

import logging
from datetime import date, datetime
from math import ceil
from pathlib import Path

from clipforge.accounts.service import env_account
from clipforge.config import Settings
from clipforge.db.engine import is_db_error
from clipforge.jobs import DictJobStore, merged_cost, new_job_id, utcnow
from clipforge.models import (
    Account,
    AccountPosting,
    ChannelProgress,
    Job,
    JobInput,
    JobMetadata,
    JobStatus,
    JobSummary,
    JobView,
    PostingOverview,
    PostStatus,
    StageName,
)
from clipforge.pipeline.steps import Deps, Step, record_job, resume, summary_of
from clipforge.posting import keepalive, queue
from clipforge.posting.backend import Posting, posting_of
from clipforge.posting.enqueue import ClipFacts, enqueue_job
from clipforge.posting.slots import next_slot
from clipforge.sanitize import redact
from clipforge.sources import hold_reason

log = logging.getLogger(__name__)


def create_job(deps: Deps, job_input: JobInput) -> Job:
    """Save a queued job and spawn its first step."""
    seed = str(job_input.source_url or job_input.telegram_file_id or job_input.source_path)
    now = utcnow()
    job = Job(job_id=new_job_id(seed, now), input=job_input, created_at=now, updated_at=now)
    deps.store.save(job)
    deps.spawner.spawn(Step.INGEST, job.job_id)
    record_job(deps, job)
    return job


def get_job_view(store: DictJobStore, root: Path, job_id: str) -> JobView:
    """The core record merged with its clips (ADR-14); falls back to metadata.json."""
    try:
        job = store.get(job_id)
    except KeyError:
        return _view_from_metadata(root, job_id)
    clips = store.clips(job_id, job.clip_ids)
    cost = merged_cost(store, job)
    return JobView(
        job_id=job.job_id,
        status=job.status,
        stage=job.stage,
        progress=job.progress,
        error=job.error,
        clips=clips,
        cost=cost,
        output_zip=job.output_zip,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _view_from_metadata(root: Path, job_id: str) -> JobView:
    path = root / job_id / "output" / "metadata.json"
    if not path.exists():
        raise KeyError(f"unknown job {job_id!r}")
    meta = JobMetadata.model_validate_json(path.read_text())
    return JobView(
        job_id=job_id,
        status=JobStatus.DONE,
        stage=StageName.PACKAGE,
        clips=[],
        cost=meta.cost,
        output_zip=f"{job_id}/job.zip",
        created_at=meta.started_at,
        updated_at=meta.finished_at,
    )


def resume_job(deps: Deps, job_id: str) -> JobView:
    """Resume a failed job; raises steps.JobNotResumable while it is queued or running."""
    resume(deps, job_id)
    return get_job_view(deps.store, deps.root, job_id)


def job_summaries(deps: Deps) -> list[JobSummary]:
    """The jobs table, or (without a database) the Dict's `job:*` records."""
    if deps.jobs_db is not None:
        return deps.jobs_db.list()
    found = []
    for job_id in deps.store.list_job_ids():
        try:
            found.append(summary_of(deps.store.get(job_id)))
        except Exception as exc:
            log.warning("skipping unreadable job %s: %s", job_id, redact(exc), exc_info=True)
    return found


def rebuild_posting(deps: Deps, now: datetime) -> int:
    """Queue every finished channel job's clips from its metadata.json (idempotent, spec §5.4)."""
    posting = deps.posting
    if posting is None:
        return 0
    added = 0
    for summary in job_summaries(deps):
        if summary.status is not JobStatus.DONE or summary.source_id is None:
            continue
        try:
            meta_path = summary.metadata_path or f"{summary.job_id}/output/metadata.json"
            meta = JobMetadata.model_validate_json((deps.root / meta_path).read_text())
            output_dir = str(Path(meta_path).parent)
            clips = [
                ClipFacts.from_packaged(c, meta.source.source_hash, output_dir) for c in meta.clips
            ]
            job = Job(
                job_id=summary.job_id, status=summary.status, input=summary.input,
                created_at=summary.created_at,
                updated_at=summary.finished_at or summary.updated_at,
            )  # fmt: skip
            added += enqueue_job(posting, job, clips, now, deps.version)
        except Exception as exc:  # files cleaned, old schema: never stops the rest
            log.warning(
                "rebuild: skipping job %s: %s",
                summary.job_id,
                redact(exc),
                exc_info=not is_db_error(exc),
            )
    return added


def restore_posting(deps: Deps, day: date | None = None) -> int:
    """Put back posting keys that expired from the Dict, from the Volume snapshot of `day`
    (default: the newest)."""
    return keepalive.restore(deps.store.kv, deps.root, day)


_EPISODE_RANK = {JobStatus.DONE: 2, JobStatus.RUNNING: 1, JobStatus.QUEUED: 1, JobStatus.FAILED: 0}


def _episode_counts(statuses: dict[str, JobStatus]) -> dict[str, int]:
    values = list(statuses.values())
    return {
        "episodes_clipped": values.count(JobStatus.DONE),
        "episodes_clipping": values.count(JobStatus.RUNNING) + values.count(JobStatus.QUEUED),
        "episodes_failed": values.count(JobStatus.FAILED),
    }


def _account_view(
    posting: Posting, account: Account, summaries: list[JobSummary], now: datetime
) -> AccountPosting:
    """One account's channels and queue. A source belongs to its account, else to account #1."""
    records = posting.repo.records(account.id)
    names: dict[str, str] = {}
    episodes: dict[str, dict[str, JobStatus]] = {}
    for s in summaries:
        if s.source_id is None:
            continue
        source = posting.source(s.source_id)
        owner = source.account_id if source else posting.default_account_id
        if owner != account.id:
            continue
        if source:
            names[s.source_id] = source.credit_name
        else:
            names[s.source_id] = s.input.channel.name if s.input.channel else s.source_id
        label = s.source_label or s.job_id
        seen = episodes.setdefault(s.source_id, {})
        if label not in seen or _EPISODE_RANK[s.status] > _EPISODE_RANK[seen[label]]:
            seen[label] = s.status
    counts: dict[str, dict[PostStatus, int]] = {}
    waiting = past = 0
    for record in records:
        sid = record.item.source_id or "none"
        names.setdefault(sid, record.item.credits[0] if record.item.credits else sid)
        state = queue.status(record)
        by_status = counts.setdefault(sid, {})
        by_status[state] = by_status.get(state, 0) + 1
        if state in (PostStatus.QUEUED, PostStatus.SKIPPED):
            if hold_reason(posting.source(sid), record.platforms, now) is not None:
                past += 1
            else:
                waiting += 1
    channels = [
        ChannelProgress(
            slug=sid, name=names[sid], **_episode_counts(episodes.get(sid, {})),
            counts=counts.get(sid, {}),
        )
        for sid in sorted(names)
    ]  # fmt: skip
    per_day = len(account.posting.slots)
    enabled = account.posting.chat_id is not None
    return AccountPosting(
        account_id=account.id, enabled=enabled, paused=posting.repo.paused(account.id),
        channels=channels, waiting=waiting, days_left=ceil(waiting / per_day) if per_day else 0,
        per_day=per_day, next_slot=next_slot(account.posting, now) if enabled else None,
        held=past, timezone=account.posting.timezone,
    )  # fmt: skip


def posting_overview(deps: Deps, settings: Settings, now: datetime) -> PostingOverview:
    """Per account, per channel: episodes by job status (a re-cut counts once, by its best job)
    and clips by posting status; plus how long the queue lasts (spec §9). The top-level fields
    are account #1's, so existing clients keep working."""
    posting = posting_of(deps)
    # Dict mode reads the POSTING_* settings as they are now (the one env account).
    accounts = (
        [env_account(settings)]
        if settings.state_reads == "dict"
        else sorted(posting.accounts(), key=lambda a: a.id)
    )
    summaries = job_summaries(deps)
    views = [_account_view(posting, a, summaries, now) for a in accounts]
    top = next((v for v in views if v.account_id == posting.default_account_id), None)
    problem = posting.problem or (
        settings.posting_problem if settings.state_reads == "dict" else None
    )
    if top is None:
        return PostingOverview(
            enabled=False, paused=False, channels=[], waiting=0, days_left=0, per_day=0,
            next_slot=None, problem=problem, accounts=views,
        )  # fmt: skip
    return PostingOverview(
        enabled=top.enabled, paused=top.paused, channels=top.channels, waiting=top.waiting,
        days_left=top.days_left, per_day=top.per_day, next_slot=top.next_slot,
        problem=problem, accounts=views,
    )  # fmt: skip
