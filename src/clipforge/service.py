"""Job service: the one entry point shared by the API, the bot and the CLI (ADR-2)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, datetime
from math import ceil
from pathlib import Path
from typing import Literal

from clipforge.accounts.service import env_account
from clipforge.config import Settings
from clipforge.db.engine import is_db_error
from clipforge.db.jobs import JobsRepo
from clipforge.jobs import DictJobStore, merged_cost, new_job_id, utcnow
from clipforge.models import (
    Account,
    AccountPosting,
    ChannelProgress,
    CostSummary,
    Job,
    JobInput,
    JobMetadata,
    JobStatus,
    JobSummary,
    JobView,
    PostingOverview,
    PostingState,
    PostStatus,
    Source,
    StageCost,
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
    job_input, note = _freeze_hooks(deps, job_input)
    job = Job(job_id=new_job_id(seed, now), input=job_input, created_at=now, updated_at=now,
              hooks_note=note)  # fmt: skip
    deps.store.save(job)
    deps.spawner.spawn(Step.INGEST, job.job_id)
    record_job(deps, job)
    return job


def _freeze_hooks(
    deps: Deps, job_input: JobInput
) -> tuple[JobInput, Literal["unavailable"] | None]:
    """Freeze the account's hook rotation on a channel job (ADR-50, hooks spec §2.1), so an
    edit mid-job never changes it. Best-effort: no database, no account or any error leaves
    the job without one, and it runs as before (the note lands in metadata.json). A rotation
    sent by the caller is never kept: only the library's own is frozen."""
    job_input = job_input.model_copy(update={"hooks": None})
    if job_input.channel is None:
        return job_input, None
    if deps.hooks is None or deps.posting is None:
        return job_input, "unavailable"
    account_id: str | None = None
    try:
        source = deps.posting.source(job_input.channel.slug)
        account_id = source.account_id if source else deps.posting.default_account_id
        rotation = deps.hooks.rotation_for(account_id, "clips")
    except Exception as exc:
        log.warning("hook rotation unavailable for %s: %s", account_id or job_input.channel.slug,
                    redact(exc))  # fmt: skip
        return job_input, "unavailable"
    return job_input.model_copy(update={"hooks": rotation}), None


def get_job_view(
    store: DictJobStore, root: Path, job_id: str, jobs_db: JobsRepo | None = None
) -> JobView:
    """The jobs table first (ADR-26, card 002 A5), with the Dict's live detail (stage, progress,
    clips, error) added while it still has the job; then the Dict alone; then metadata.json.
    The newer record wins: a Dict record updated after the row (a resume whose row write
    failed, say) is shown as is, and a tie goes to the table."""
    row = _job_row(jobs_db, job_id)
    try:
        job: Job | None = store.get(job_id)
    except KeyError:
        job = None
    if job is not None and (row is None or job.updated_at > row.updated_at):
        return _live_view(store, job)
    if row is not None:
        return _view_from_row(store, root, jobs_db, row, job)
    return _view_from_metadata(root, job_id)


def _job_row(jobs_db: JobsRepo | None, job_id: str) -> JobSummary | None:
    if jobs_db is None:
        return None
    try:
        return jobs_db.get(job_id)
    except Exception as exc:
        if not is_db_error(exc):
            raise
        log.warning("reading the jobs row of %s failed: %s", job_id, redact(exc))
        return None


def _live_view(store: DictJobStore, job: Job) -> JobView:
    return JobView(
        job_id=job.job_id,
        status=job.status,
        stage=job.stage,
        progress=job.progress,
        error=job.error,
        clips=store.clips(job.job_id, job.clip_ids),
        cost=merged_cost(store, job),
        output_zip=job.output_zip,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _metadata_stages(root: Path, metadata_path: str) -> list[StageCost]:
    """The per-stage breakdown in a done job's metadata.json (empty if it can't be read)."""
    try:
        path = root / metadata_path
        return list(JobMetadata.model_validate_json(path.read_text()).cost.stages)
    except Exception as exc:
        log.warning("reading %s failed: %s", metadata_path, redact(exc))
        return []


def _view_from_row(
    store: DictJobStore, root: Path, jobs_db: JobsRepo | None, row: JobSummary, job: Job | None
) -> JobView:
    """Status, times and cost from the row; the stage breakdown from the `costs` rows, else
    metadata.json, else the Dict's; clips, error and progress only while the Dict has them."""
    stages: list[StageCost] = []
    if jobs_db is not None:
        try:
            stages = jobs_db.costs(row.job_id)
        except Exception as exc:
            if not is_db_error(exc):
                raise
            log.warning("reading the costs of %s failed: %s", row.job_id, redact(exc))
    if not stages and row.metadata_path is not None:
        stages = _metadata_stages(root, row.metadata_path)
    if not stages and job is not None:
        stages = merged_cost(store, job).stages
    # nothing else: a made-up stage line would skew per-stage sums (the dashboard adds them up)
    done = row.status is JobStatus.DONE
    zip_path = f"{row.job_id}/job.zip" if done else None
    return JobView(
        job_id=row.job_id,
        status=row.status,
        stage=job.stage if job is not None else (StageName.PACKAGE if done else None),
        progress=job.progress if job is not None else None,
        error=job.error if job is not None else None,
        clips=store.clips(job.job_id, job.clip_ids) if job is not None else [],
        cost=CostSummary(stages=stages),
        output_zip=job.output_zip if job is not None else zip_path,
        created_at=row.created_at,
        updated_at=row.updated_at,
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
    return get_job_view(deps.store, deps.root, job_id, deps.jobs_db)


def job_summaries(deps: Deps) -> list[JobSummary]:
    """The jobs table first (card 002 A5), plus any Dict `job:*` record the table lacks (a row
    not written yet, or before the backfill) or that is newer than its row. If the table can't
    be read, the Dict alone."""
    found: dict[str, JobSummary] = {}
    if deps.jobs_db is not None:
        try:
            found = {s.job_id: s for s in deps.jobs_db.list()}
        except Exception as exc:
            if not is_db_error(exc):
                raise
            log.warning("reading the jobs table failed, using the Dict: %s", redact(exc))
    for job_id, raw in deps.store.job_records():
        try:
            live = summary_of(Job.model_validate_json(raw))
        except Exception as exc:
            log.warning("skipping unreadable job %s: %s", job_id, redact(exc), exc_info=True)
            continue
        row = found.get(job_id)
        if row is None:
            found[job_id] = live
        elif live.updated_at > row.updated_at:
            # the same rule as get_job_view: a newer Dict record (a row write that failed after
            # a resume or a DONE save) wins; the row keeps what only it knows
            found[job_id] = live.model_copy(update={
                "metadata_path": live.metadata_path or row.metadata_path,
                "build": live.build or row.build, "cost_usd": live.cost_usd or row.cost_usd,
            })  # fmt: skip
    return [found[job_id] for job_id in sorted(found)]


class PostingOutage(Exception):
    """A rebuild while the outage flag is set: expired posted/verdict keys could re-queue clips
    (decision log #217). The message says how to clear it."""

    def __init__(self, since: str) -> None:
        super().__init__(
            f"Outage: posting_daily didn't run since {since}, so Dict keys may have expired and "
            f"rebuild is stopped. Restore from that snapshot (clipforge status --restore {since}), "
            "check /status, then /go; rebuild after that."
        )
        self.since = since


def rebuild_posting(deps: Deps, now: datetime) -> int:
    """Queue every finished channel job's clips from its metadata.json (idempotent, spec §5.4).
    Raises PostingOutage while the outage flag is set, like posting_daily (#217)."""
    posting = deps.posting
    if posting is None:
        return 0
    since = keepalive.outage_since(deps.store.kv)
    if since is not None:
        raise PostingOutage(since)
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
            added += enqueue_job(posting, job, clips, now, deps.version,
                                 flag_on=deps.hook_variants)  # fmt: skip
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
    restored = keepalive.restore(deps.store.kv, deps.root, day)
    keepalive.clear_outage(deps.store.kv)  # the owner restored: posting can resume
    return restored


_EPISODE_RANK = {JobStatus.DONE: 2, JobStatus.RUNNING: 1, JobStatus.QUEUED: 1, JobStatus.FAILED: 0}


def _episode_counts(statuses: dict[str, JobStatus]) -> dict[str, int]:
    values = list(statuses.values())
    return {
        "episodes_clipped": values.count(JobStatus.DONE),
        "episodes_clipping": values.count(JobStatus.RUNNING) + values.count(JobStatus.QUEUED),
        "episodes_failed": values.count(JobStatus.FAILED),
    }


def _account_view(
    posting: Posting,
    account: Account,
    summaries: list[JobSummary],
    source: Callable[[str], Source | None],
    now: datetime,
) -> AccountPosting:
    """One account's channels and queue. A source belongs to its account, else to account #1.
    `source` is the overview's lookup, read once per request."""
    records = posting.repo.records(account.id)
    names: dict[str, str] = {}
    episodes: dict[str, dict[str, JobStatus]] = {}
    for s in summaries:
        if s.source_id is None:
            continue
        found = source(s.source_id)
        owner = found.account_id if found else posting.default_account_id
        if owner != account.id:
            continue
        if found:
            names[s.source_id] = found.credit_name
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
            if hold_reason(source(sid), record.platforms, now) is not None:
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
    paused = posting.repo.paused(account.id)
    unanswered = len(queue.unanswered(records))
    sends = [send.at for record in records for send in record.sends]
    account_state: PostingState = (
        "off" if not enabled else "paused" if paused
        else "waiting" if unanswered >= queue.PAUSE_AFTER else "on"
    )  # fmt: skip
    return AccountPosting(
        account_id=account.id, enabled=enabled, paused=paused,
        channels=channels, waiting=waiting, days_left=ceil(waiting / per_day) if per_day else 0,
        per_day=per_day, next_slot=next_slot(account.posting, now) if enabled else None,
        held=past, timezone=account.posting.timezone, state=account_state,
        posted_total=sum(queue.status(r) is PostStatus.POSTED for r in records),
        unanswered=unanswered, last_sent_at=max(sends, default=None),
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
    source = posting.source_lookup()
    views = [_account_view(posting, a, summaries, source, now) for a in accounts]
    top = next((v for v in views if v.account_id == posting.default_account_id), None)
    problem = posting.problem or (
        settings.posting_problem if settings.state_reads == "dict" else None
    )
    posted_total = sum(v.posted_total for v in views)
    outage = keepalive.outage_since(deps.store.kv)
    if top is None:
        return PostingOverview(
            enabled=False, paused=False, channels=[], waiting=0, days_left=0, per_day=0,
            next_slot=None, problem=problem, accounts=views,
            state="problem" if problem else "off", posted_total=posted_total,
            outage_since=outage,
        )  # fmt: skip
    return PostingOverview(
        enabled=top.enabled, paused=top.paused, channels=top.channels, waiting=top.waiting,
        days_left=top.days_left, per_day=top.per_day, next_slot=top.next_slot,
        problem=problem, accounts=views,
        state="problem" if problem else "outage" if outage else top.state,
        posted_total=posted_total, outage_since=outage,
    )  # fmt: skip
