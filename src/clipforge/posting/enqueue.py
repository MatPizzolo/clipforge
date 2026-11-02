"""Put a finished channel job's clips into the posting queue (spec §4)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from clipforge.hooks.rotation import stamp_for
from clipforge.models import (
    Account,
    AssetSource,
    ClipOrigin,
    ContentItem,
    HookResult,
    HookRotation,
    Job,
    PackagedClip,
    Platform,
    PostRecord,
    RenderedClip,
    Source,
)
from clipforge.posting.backend import Posting
from clipforge.posting.queue import overlaps
from clipforge.posting.repo import PostingRepo
from clipforge.sources import source_problem, uncovered

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClipFacts:
    clip_id: str
    rank: int
    source_hash: str
    start: float
    end: float
    score: float
    title: str
    hook: str
    video_path: str  # relative to JOBS_ROOT
    hook_result: HookResult | None = None  # the title card's hook (HK-2's drawn result)

    @classmethod
    def from_rendered(cls, r: RenderedClip) -> ClipFacts:
        c = r.spec.candidate
        return cls(r.clip_id, r.spec.rank, r.spec.source.source_hash, r.spec.start, r.spec.end,
                   c.score, c.title, c.hook, r.video_path, r.hook)  # fmt: skip

    @classmethod
    def from_packaged(cls, c: PackagedClip, source_hash: str, output_dir: str) -> ClipFacts:
        hook = c.hook_stamp.result if c.hook_stamp is not None else None
        return cls(c.clip_id, c.rank, source_hash, c.start, c.end, c.score, c.title, c.hook,
                   f"{output_dir}/{c.video}", hook)  # fmt: skip


def platforms_for(account: Account) -> list[Platform]:
    return [p for p in Platform if (prof := account.platforms.get(p)) is not None and prof.enabled]


def items_for(job: Job, clips: list[ClipFacts], now: datetime, account: Account,
              source: Source | None, version: str, *, rotation: HookRotation | None = None,
              flag_on: bool = False) -> list[ContentItem]:  # fmt: skip
    """`rotation` is the job's frozen one (`job.input.hooks`): each item is stamped with the
    control, or with its drawn result once HOOK_VARIANTS is on (ADR-50)."""
    channel = job.input.channel
    if channel is None:
        return []
    credit = source.credit_name if source else channel.name
    permission = source.permission.type if source else job.input.permission
    sponsored = bool(source and source.campaign and source.campaign.sponsored)
    stamps = {c.clip_id: stamp_for(rotation, c.title, c.hook_result, flag_on=flag_on)
              for c in clips}  # fmt: skip
    return [
        ContentItem(
            id=f"{job.job_id}:{c.clip_id}",
            account_id=account.id,
            source_id=channel.slug,
            producer_version=version,
            language=account.language,
            video_path=c.video_path,
            duration=c.end - c.start,
            title=stamps[c.clip_id][1],
            hook=c.hook,
            score=c.score,
            credits=[credit],
            sponsored=sponsored,
            assets=[
                AssetSource(
                    kind="source_video",
                    license=permission.value,
                    attribution=credit,
                    url=str(source.url) if source and source.url else None,
                )
            ],
            clip=ClipOrigin(
                job_id=job.job_id,
                clip_id=c.clip_id,
                source_hash=c.source_hash,
                start=c.start,
                end=c.end,
                episode=job.input.source_label or job.job_id,
                episode_finished_at=job.updated_at,
            ),
            queued_at=now,
            hook_stamp=stamps[c.clip_id][0],
        )
        for c in sorted(clips, key=lambda c: c.rank)
    ]


def enqueue(repo: PostingRepo, items: list[ContentItem], platforms: list[Platform]) -> int:
    """Add each item unless a non-rejected clip of the same video covers its moment."""
    if not items:
        return 0
    first = items[0].clip
    records = repo.records_for_source(first.source_hash) if first else []
    added = 0
    for item in items:
        if overlaps(item, records):
            continue
        if repo.add(item, platforms):
            added += 1
            records.append(PostRecord(item=item, platforms=platforms))
    return added


def enqueue_job(
    posting: Posting,
    job: Job,
    clips: list[ClipFacts],
    now: datetime,
    version: str,
    *,
    flag_on: bool = False,
) -> int:
    channel = job.input.channel
    if channel is None:
        return 0
    source = posting.source(channel.slug)
    if source is None and posting.requires_source:
        log.warning("posting: no source %r; add it with `clipforge source add`, then run "
                    "`clipforge status --rebuild`", channel.slug)  # fmt: skip
        return 0
    if source is not None and (problem := source_problem(source, now)) is not None:
        log.warning("posting: not queueing %s from %s: %s", job.job_id, source.id, problem)
        return 0  # `clipforge status --rebuild` queues it once the source is fixed
    account = posting.account(source.account_id if source else posting.default_account_id)
    if account is None:
        log.warning("posting: %s belongs to an account this mode doesn't serve", channel.slug)
        return 0
    platforms = platforms_for(account)
    if source is not None and (missing := uncovered(source, platforms)):
        log.warning("posting: %s's permission doesn't cover %s; not queued there",
                    source.id, ", ".join(missing))  # fmt: skip
        platforms = [p for p in platforms if p not in missing]
        if not platforms:
            return 0
    items = items_for(job, clips, now, account, source, version, rotation=job.input.hooks,
                      flag_on=flag_on)  # fmt: skip
    return enqueue(posting.repo, items, platforms)
