"""What the Modal smoke job must deliver, checked against metadata.json."""

from __future__ import annotations

from datetime import UTC, datetime

from clipforge.models import (
    CostSummary,
    JobError,
    JobMetadata,
    JobStatus,
    JobView,
    StageCost,
    StageName,
)
from clipforge.smoke import check_smoke, smoke_input
from tests.test_models import ALL_SAMPLES

AT = datetime(2026, 9, 23, tzinfo=UTC)


def _meta(**probe: object) -> JobMetadata:
    meta = next(m for m in ALL_SAMPLES if isinstance(m, JobMetadata))
    clip = meta.clips[0]
    good = {
        "width": 1080,
        "height": 1920,
        "duration_s": 7.0,
        "n_video_streams": 1,
        "n_audio_streams": 1,
        "size_bytes": 2_000_000,
    }
    clip = clip.model_copy(update={"probe": clip.probe.model_copy(update={**good, **probe})})
    cost = CostSummary(
        stages=[StageCost(stage=StageName.TRANSCRIBE, gpu_s=4.0, usd_estimate=0.001)]
    )
    return meta.model_copy(update={"clips": [clip], "cost": cost})


def _view(status: JobStatus, error: JobError | None = None) -> JobView:
    return JobView(
        job_id="J",
        status=status,
        stage=StageName.PACKAGE,
        clips=[],
        cost=CostSummary(),
        created_at=AT,
        updated_at=AT,
        error=error,
    )


def test_smoke_input_is_one_short_clip() -> None:
    job_input = smoke_input("smoke/abc/talking_head_10s.mp4")
    assert job_input.source_path == "smoke/abc/talking_head_10s.mp4"
    # The fixture is one ~10 s passage; Haiku proposes all of it, so max_len must allow that.
    assert (job_input.options.n, job_input.options.min_len, job_input.options.max_len) == (
        1,
        5.0,
        12.0,
    )


def test_good_job_passes() -> None:
    assert check_smoke(_view(JobStatus.DONE), _meta()) == []


def test_failed_job_reports_stage_and_reason() -> None:
    error = JobError(stage=StageName.HIGHLIGHTS, error_type="permanent", message="no clips")
    assert check_smoke(_view(JobStatus.FAILED, error), None) == [
        "job failed at highlights: no clips"
    ]


def test_bad_clip_properties_are_listed() -> None:
    problems = check_smoke(_view(JobStatus.DONE), _meta(width=720, duration_s=13.0))
    assert any("1080x1920" in p for p in problems)
    assert any("duration" in p for p in problems)


def test_missing_gpu_cost_is_a_problem() -> None:
    meta = _meta().model_copy(update={"cost": CostSummary()})
    assert any("GPU" in p for p in check_smoke(_view(JobStatus.DONE), meta))


def test_cached_transcription_passes() -> None:
    # Re-runs hit the transcribe cache (keyed on the fixture's hash): no new GPU seconds.
    cached = CostSummary(stages=[StageCost(stage=StageName.TRANSCRIBE, cached=True)])
    meta = _meta().model_copy(update={"cost": cached})
    assert check_smoke(_view(JobStatus.DONE), meta) == []
