"""TelegramNotifier and the message texts, driven through the real step chain."""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

from clipforge.bot import messages
from clipforge.bot.notifier import TelegramNotifier
from clipforge.links import verify
from clipforge.models import (
    CostSummary,
    Job,
    JobError,
    JobStatus,
    JobView,
    Progress,
    StageName,
    TelegramTarget,
)
from tests.bot.fakes import CHAT, FakeSender, make_settings
from tests.pipeline.harness import Harness

TARGET = TelegramTarget(chat_id=CHAT, reply_to_message_id=3)


def _wire(harness: Harness, **settings: object) -> FakeSender:
    sender = FakeSender()
    config = make_settings(harness.root, **settings)
    harness.deps.notifier_for = lambda job: TelegramNotifier(
        sender, TARGET, harness.store, config, harness.root
    )
    return sender


def test_chain_sends_each_clip_then_the_zip_link(harness: Harness) -> None:
    sender = _wire(harness)
    job_id = harness.submit()
    harness.run()

    assert len(sender.videos) == 5
    chat, path, caption, reply_to = sender.videos[0]
    assert (chat, reply_to) == (CHAT, 3)
    assert path.is_relative_to(harness.root) and path.name == "clip.mp4"
    assert caption.startswith("#") and " · score " in caption

    chat, text, reply_to = sender.messages[-1]
    assert text.startswith("5 of 5 clips · $")
    url = text.rsplit(" · ", 1)[-1]
    query = parse_qs(urlsplit(url).query)
    assert f"/jobs/{job_id}/download" in url
    assert verify("k3y", job_id, int(query["exp"][0]), query["sig"][0])


def test_done_without_link_config(harness: Harness) -> None:
    sender = _wire(harness, api_url=None)
    harness.submit()
    harness.run()
    assert sender.messages[-1][1].startswith("5 of 5 clips")
    assert "not set" in sender.messages[-1][1]


def test_failed_message_names_stage_and_resume(harness: Harness) -> None:
    sender = _wire(harness)
    harness.stages.permanent["transcribe"] = "no speech found"
    job_id = harness.submit()
    harness.run()
    assert sender.messages == [(CHAT, f"transcribe: no speech found\n/resume {job_id}", 3)]


def test_done_and_failed_link_to_the_job_page_when_the_dashboard_is_set(harness: Harness) -> None:
    # card 002 A4 (ADR-44): a "Job ↗" button, none without DASHBOARD_URL (tests above)
    sender = _wire(harness, dashboard_url="https://dash.example")
    harness.stages.permanent["transcribe"] = "no speech found"
    job_id = harness.submit()
    harness.run()
    [(_, _, _)] = sender.messages
    [buttons] = [b for b in sender.keyboards.values() if b is not None]
    assert buttons == [[("Job ↗", f"https://dash.example/jobs/{job_id}")]]


def test_status_text() -> None:
    at = datetime(2026, 9, 23, tzinfo=UTC)
    view = JobView(
        job_id="J",
        status=JobStatus.RUNNING,
        stage=StageName.TRANSCRIBE,
        progress=Progress(stage=StageName.TRANSCRIBE, pct=40, message="transcribing", at=at),
        clips=[],
        cost=CostSummary(),
        created_at=at,
        updated_at=at,
    )
    assert messages.status_text(view) == (
        "job J: running\nstage: transcribe 40% transcribing\ncost: $0.000"
    )


def test_failed_text_without_error_record() -> None:
    at = datetime(2026, 9, 23, tzinfo=UTC)
    job = Job.model_validate(
        {
            "job_id": "J",
            "input": {"source_url": "https://a.example/v.mp4", "permission": "own"},
            "created_at": at,
            "updated_at": at,
            "status": "failed",
            "error": JobError(stage=StageName.INGEST, error_type="x", message="bad").model_dump(),
        }
    )
    assert messages.failed_text(job) == "ingest: bad\n/resume J"
