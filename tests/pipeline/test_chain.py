import threading
from collections import Counter
from pathlib import Path

from clipforge.jobs import load_ref
from clipforge.models import (
    ClipSpec,
    ClipState,
    ClipStatus,
    Job,
    JobStatus,
    RenderedClip,
    StageName,
)
from clipforge.pipeline.deps import RecordingNotifier
from clipforge.pipeline.steps import Step, dispatch, sanitize
from tests.pipeline.fakes import FakeStages
from tests.pipeline.harness import Harness


class ExplodingNotifier:
    def clip_ready(self, job: object, clip: object, rendered: object) -> None:
        raise RuntimeError("telegram down")

    def done(self, job: object) -> None:
        raise RuntimeError("telegram down")

    def failed(self, job: object) -> None:
        raise RuntimeError("telegram down")


# ---- happy path and caching


def test_happy_path(harness: Harness) -> None:
    job_id = harness.submit()
    harness.run()
    job = harness.store.get(job_id)
    assert job.status is JobStatus.DONE
    assert job.output_zip is not None and (harness.root / job.output_zip).exists()
    assert job.clip_ids == [f"clip_{i:02d}" for i in range(1, 6)]
    assert set(job.outputs) == {
        StageName.INGEST,
        StageName.TRANSCRIBE,
        StageName.HIGHLIGHTS,
        StageName.PACKAGE,
    }
    clips = harness.store.clips(job_id, job.clip_ids)
    assert all(c.status is ClipStatus.DONE and c.telegram_sent for c in clips)
    kinds = harness.event_kinds()
    assert kinds.count("clip_ready") == 5 and kinds.count("done") == 1 and kinds[-1] == "done"
    assert harness.stages.calls["package"] == 1 and harness.retries_seen == 0
    assert harness.volume.commits >= 5 and harness.volume.reloads >= 9


def test_clip_specs_are_job_scoped_and_ranked(harness: Harness) -> None:
    job_id = harness.submit()
    harness.run()
    spec_file = harness.root / job_id / "clips" / "clip_01.json"
    spec = ClipSpec.model_validate_json(spec_file.read_text())
    assert spec.rank == 1 and spec.candidate.score == 0.9 and spec.start == 10.0


def test_second_job_reuses_cached_stages(harness: Harness) -> None:
    harness.submit()
    harness.run()
    second = harness.submit(n=3)
    harness.run()
    job = harness.store.get(second)
    assert job.status is JobStatus.DONE and len(job.clip_ids) == 3
    computes = harness.stages.computes
    assert (computes["ingest"], computes["transcribe"], computes["highlights"]) == (1, 1, 1)
    assert computes["clip"] == 5  # the second job's 3 clips all came from the cache
    cached = {c.stage for c in job.cost.stages if c.cached}
    assert {StageName.INGEST, StageName.TRANSCRIBE, StageName.HIGHLIGHTS} <= cached


def test_cached_clip_is_rebound_to_this_jobs_spec(harness: Harness) -> None:
    harness.submit()
    harness.run()
    harness.stages.reverse = True  # same five ranges, opposite ranking
    second = harness.submit()
    harness.run()
    assert harness.stages.computes["clip"] == 5  # every range reused from the cache
    state = harness.store.get_clip(second, "clip_01")
    assert state.result_ref is not None
    rendered = load_ref(harness.root, state.result_ref, RenderedClip)
    assert rendered.clip_id == "clip_01"
    assert rendered.spec.rank == 1 and rendered.spec.start == 250.0  # best range in job 2


# ---- review focus: duplicates, stale and unknown steps


def test_duplicate_spawns_do_not_duplicate_work(harness: Harness) -> None:
    job_id = harness.submit()
    harness.spawner.spawn(Step.INGEST, job_id)  # Modal delivers a spawn twice
    harness.run()
    kinds = harness.event_kinds()
    assert kinds.count("done") == 1 and kinds.count("clip_ready") == 5
    assert harness.stages.calls["package"] == 1
    assert [c.step for c in harness.spawner.spawned].count(Step.PACKAGE) == 1
    assert harness.store.get(job_id).status is JobStatus.DONE


def test_steps_for_a_failed_job_do_nothing(tmp_path: Path) -> None:
    h = Harness.build(tmp_path, FakeStages(permanent={"ingest": "not a direct media link"}))
    job_id = h.submit()
    h.run()
    dispatch(h.deps, Step.TRANSCRIBE, job_id)
    dispatch(h.deps, Step.CLIP, job_id, "clip_01")
    assert h.stages.calls["transcribe"] == 0 and h.stages.calls["clip_01"] == 0
    assert not h.spawner.queue


def test_step_for_unknown_job_is_ignored(harness: Harness) -> None:
    dispatch(harness.deps, Step.TRANSCRIBE, "20260923-deadbeef-0000")
    assert not harness.spawner.queue and harness.stages.calls["transcribe"] == 0


# ---- errors (ADR-15)


def test_permanent_error_fails_at_once(tmp_path: Path) -> None:
    h = Harness.build(tmp_path, FakeStages(permanent={"ingest": "not a direct media link"}))
    job_id = h.submit()
    h.run()
    job = h.store.get(job_id)
    assert job.status is JobStatus.FAILED and job.error is not None
    assert (job.error.stage, job.error.error_type) == (StageName.INGEST, "permanent")
    assert job.error.message == "not a direct media link"
    assert h.stages.calls["ingest"] == 1 and h.retries_seen == 0
    assert h.event_kinds() == ["failed"]


def test_transient_error_is_retried(tmp_path: Path) -> None:
    h = Harness.build(tmp_path, FakeStages(transient=Counter({"transcribe": 2})))
    job_id = h.submit()
    h.run()
    assert h.store.get(job_id).status is JobStatus.DONE
    assert h.stages.calls["transcribe"] == 3 and h.retries_seen == 2


def test_gives_up_after_max_attempts(tmp_path: Path) -> None:
    h = Harness.build(tmp_path, FakeStages(transient=Counter({"transcribe": 99})))
    job_id = h.submit()
    h.run()
    job = h.store.get(job_id)
    assert job.status is JobStatus.FAILED and job.error is not None
    assert (job.error.stage, job.error.error_type) == (StageName.TRANSCRIBE, "RuntimeError")
    assert job.error.message == "RuntimeError: transcribe blip"
    assert h.stages.calls["transcribe"] == 3 and h.retries_seen == 2
    assert h.event_kinds() == ["failed"]


def test_one_clip_failing_does_not_stop_the_others(tmp_path: Path) -> None:
    h = Harness.build(tmp_path, FakeStages(permanent={"clip_03": "corrupt frame"}))
    job_id = h.submit()
    h.run()
    job = h.store.get(job_id)
    assert job.status is JobStatus.DONE
    failed = h.store.get_clip(job_id, "clip_03")
    assert failed.status is ClipStatus.FAILED and failed.error is not None
    assert (failed.error.stage, failed.error.message) == (StageName.RENDER, "corrupt frame")
    assert h.stages.packaged == ["clip_01", "clip_02", "clip_04", "clip_05"]
    kinds = h.event_kinds()
    assert kinds.count("clip_ready") == 4 and kinds.count("done") == 1


def test_all_clips_failing_fails_the_job(tmp_path: Path) -> None:
    fail_all = {f"clip_{i:02d}": "boom" for i in range(1, 6)}
    h = Harness.build(tmp_path, FakeStages(permanent=fail_all))
    job_id = h.submit()
    h.run()
    job = h.store.get(job_id)
    assert job.status is JobStatus.FAILED and job.error is not None
    assert (job.error.stage, job.error.message) == (StageName.PACKAGE, "all 5 clips failed")
    assert h.event_kinds() == ["failed"]


def test_no_candidates_fails_highlights(tmp_path: Path) -> None:
    h = Harness.build(tmp_path, FakeStages(n_candidates=0))
    job_id = h.submit()
    h.run()
    job = h.store.get(job_id)
    assert job.status is JobStatus.FAILED and job.error is not None
    assert job.error.stage is StageName.HIGHLIGHTS
    assert job.error.message == "no clip-worthy segments found in this video"


def test_notifier_failure_does_not_fail_the_job(harness: Harness) -> None:
    harness.deps.notifier_for = lambda job: ExplodingNotifier()
    job_id = harness.submit()
    harness.run()
    assert harness.store.get(job_id).status is JobStatus.DONE


def test_fan_in_spawns_package_exactly_once_under_concurrency(tmp_path: Path) -> None:
    h = Harness.build(tmp_path)
    # Hold every clip thread after it has marked its clip done and before it checks the
    # fan-in, so all five really race for the package claim.
    barrier = threading.Barrier(5)

    class BarrierNotifier(RecordingNotifier):
        def clip_ready(self, job: Job, clip: ClipState, rendered: RenderedClip) -> None:
            super().clip_ready(job, clip, rendered)
            barrier.wait(timeout=5)

    notifier = BarrierNotifier()
    h.deps.notifier_for = lambda job: notifier
    job_id = h.submit()
    h.run_until(Step.CLIP)
    clip_calls = [h.spawner.queue.popleft() for _ in range(5)]
    assert not h.spawner.queue
    threads = [
        threading.Thread(target=dispatch, args=(h.deps, c.step, c.job_id, c.clip_id))
        for c in clip_calls
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert [c.step for c in h.spawner.queue] == [Step.PACKAGE]
    h.run()
    assert h.store.get(job_id).status is JobStatus.DONE
    assert [c.step for c in h.spawner.spawned].count(Step.PACKAGE) == 1


def test_sanitize_strips_query_strings_and_caps_length() -> None:
    message = "404 for https://cdn.example.com/v.mp4?token=abc123 while downloading"
    assert sanitize(message) == "404 for https://cdn.example.com/v.mp4 while downloading"
    assert len(sanitize("x" * 1000)) == 300


def test_auto_with_no_candidate_above_threshold_fails_clearly(harness: Harness) -> None:
    job_id = harness.submit(n=None, min_score=0.95)  # fake scores top out at 0.9
    harness.run()
    job = harness.store.get(job_id)
    assert job.status is JobStatus.FAILED and job.error is not None
    assert job.error.stage is StageName.HIGHLIGHTS
    assert "0.95" in job.error.message and "0.90" in job.error.message
    assert "--min-score" in job.error.message
