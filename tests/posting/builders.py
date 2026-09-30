"""Builders for posting tests."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from clipforge.models import (
    LEGACY_PLATFORMS,
    AssetSource,
    ChannelRef,
    ClipOrigin,
    ContentItem,
    JobInput,
    Platform,
    PostRecord,
    PostSend,
    PostVerdict,
)
from clipforge.service import create_job
from tests.pipeline.harness import SOURCE_URL, Harness

T0 = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
JOB = "20260928-aaaaaaaa-0001"
BILLY = ChannelRef(slug="billy-garton", name="Billy Garton Jr.")
ACCOUNT = "realtalk-clips-en"


def item(
    clip_id: str = "clip_01",
    *,
    job_id: str = JOB,
    source_hash: str = "a" * 64,
    start: float = 0.0,
    end: float = 30.0,
    score: float = 0.85,
    channel: str = "billy-garton",
    name: str = "Billy Garton Jr.",
    finished_at: datetime = T0,
    title: str = "A title",
    hook: str = "A hook.",
    episode: str = "ep01",
    account: str = ACCOUNT,
) -> ContentItem:
    return ContentItem(
        id=f"{job_id}:{clip_id}", account_id=account, source_id=channel,
        producer_version="plan-c", language="en", video_path=f"cache/clip/{clip_id}/clip.mp4",
        duration=end - start, title=title, hook=hook, score=score, credits=[name],
        assets=[AssetSource(kind="source_video", license="unrecorded", attribution=name)],
        clip=ClipOrigin(job_id=job_id, clip_id=clip_id, source_hash=source_hash, start=start,
                        end=end, episode=episode, episode_finished_at=finished_at),
        queued_at=finished_at,
    )  # fmt: skip


def send(n: int = 1, at: datetime = T0, message_id: int = 100) -> PostSend:
    return PostSend(n=n, at=at, slot=None, message_id=message_id, video_message_id=message_id - 1)


def record(
    it: ContentItem,
    *,
    platforms: Iterable[Platform] = LEGACY_PLATFORMS,
    sends: Iterable[PostSend] = (),
    posted: Iterable[Platform] = (),
    verdict: PostVerdict | None = None,
    unavailable: bool = False,
) -> PostRecord:
    return PostRecord(
        item=it, platforms=list(platforms), sends=list(sends), posted={p: T0 for p in posted},
        verdict=verdict, unavailable=unavailable,
    )  # fmt: skip


def run_channel_job(harness: Harness, channel: ChannelRef | None = BILLY) -> str:
    """Create a 3-clip channel job the way `clipforge clip` does and run the chain to done."""
    job_input = JobInput.model_validate(
        {"source_url": SOURCE_URL, "permission": "creator_agreement", "options": {"n": 3},
         "source_label": "ep01", "channel": channel.model_dump() if channel else None}
    )  # fmt: skip
    job_id = create_job(harness.deps, job_input).job_id
    harness.run()
    return job_id
