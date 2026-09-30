from collections import Counter
from datetime import timedelta
from pathlib import Path

import pytest

from clipforge.models import ClipStatus, JobStatus
from clipforge.pipeline.steps import JobNotResumable, Step, resume, sweep
from tests.pipeline.fakes import FakeStages
from tests.pipeline.harness import Harness


def test_resume_continues_from_first_incomplete_step(tmp_path: Path) -> None:
    stages = FakeStages(transient=Counter({"transcribe": 99}))
    h = Harness.build(tmp_path, stages)
    job_id = h.submit()
    h.run()
    assert h.store.get(job_id).status is JobStatus.FAILED
    stages.transient.clear()
    assert resume(h.deps, job_id) is Step.TRANSCRIBE
    h.run()
    job = h.store.get(job_id)
    assert job.status is JobStatus.DONE and job.error is None
    assert stages.computes["ingest"] == 1  # not redone
    kinds = h.event_kinds()
    assert kinds[0] == "failed" and kinds.count("clip_ready") == 5 and kinds[-1] == "done"


def test_resume_after_package_failure_skips_clips(tmp_path: Path) -> None:
    stages = FakeStages(transient=Counter({"package": 99}))
    h = Harness.build(tmp_path, stages)
    job_id = h.submit()
    h.run()
    assert h.store.get(job_id).status is JobStatus.FAILED
    stages.transient.clear()
    assert resume(h.deps, job_id) is Step.PACKAGE
    h.run()
    assert h.store.get(job_id).status is JobStatus.DONE
    assert stages.calls["clip_01"] == 1 and stages.computes["clip"] == 5


def test_resume_reruns_failed_clips(tmp_path: Path) -> None:
    stages = FakeStages(permanent={f"clip_{i:02d}": "boom" for i in range(1, 6)})
    h = Harness.build(tmp_path, stages)
    job_id = h.submit()
    h.run()
    assert h.store.get(job_id).status is JobStatus.FAILED
    stages.permanent.clear()
    assert resume(h.deps, job_id) is Step.CLIP
    h.run()
    job = h.store.get(job_id)
    assert job.status is JobStatus.DONE
    assert all(c.status is ClipStatus.DONE for c in h.store.clips(job_id, job.clip_ids))
    assert stages.calls["clip_01"] == 2


def test_resume_rules(harness: Harness) -> None:
    job_id = harness.submit()
    with pytest.raises(JobNotResumable):
        resume(harness.deps, job_id)  # still queued
    harness.run()
    assert resume(harness.deps, job_id) is None  # done: nothing to do
    assert not harness.spawner.queue


def test_sweeper_fails_stalled_jobs(harness: Harness) -> None:
    job_id = harness.submit()
    harness.spawner.queue.clear()  # the ingest spawn was lost
    start = harness.store.get(job_id).updated_at
    assert sweep(harness.deps, now=start + timedelta(minutes=19)) == []  # 15 + 5 margin
    assert sweep(harness.deps, now=start + timedelta(minutes=21)) == [job_id]
    job = harness.store.get(job_id)
    assert job.status is JobStatus.FAILED and job.error is not None
    assert job.error.error_type == "stalled"
    assert job.error.message.startswith("stalled at ingest")
    assert harness.event_kinds() == ["failed"]
    assert sweep(harness.deps, now=start + timedelta(hours=2)) == []  # already failed
    assert resume(harness.deps, job_id) is Step.INGEST
    harness.run()
    assert harness.store.get(job_id).status is JobStatus.DONE


def test_sweeper_counts_clip_activity(harness: Harness) -> None:
    job_id = harness.submit()
    harness.run_until(Step.CLIP)
    harness.spawner.queue.clear()  # clip spawns lost
    job = harness.store.get(job_id)
    start = job.updated_at
    busy = harness.store.get_clip(job_id, "clip_01").model_copy(
        update={"updated_at": start + timedelta(minutes=14)}
    )
    harness.store.save_clip(job_id, busy)
    assert sweep(harness.deps, now=start + timedelta(minutes=16)) == []  # clip active 2 min ago
    assert sweep(harness.deps, now=start + timedelta(minutes=14 + 16)) == [job_id]
    job = harness.store.get(job_id)
    assert job.error is not None and job.error.message.startswith("stalled at render")
