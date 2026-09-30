from pathlib import Path

import pytest

from clipforge.db.engine import Database
from clipforge.db.jobs import JobsRepo
from clipforge.models import JobInput, JobStatus, StageName
from clipforge.pipeline.steps import Step, fail_job, resume
from clipforge.service import create_job
from tests.pipeline.harness import SOURCE_URL, Harness
from tests.posting.builders import run_channel_job


def test_jobs_rows_follow_create_done_and_failed(tmp_path: Path, db: Database) -> None:
    harness = Harness.build(tmp_path)
    harness.deps.jobs_db = JobsRepo(db)
    job_id = run_channel_job(harness)
    done = JobsRepo(db).get(job_id)
    assert done is not None and done.status is JobStatus.DONE and done.source_id == "billy-garton"
    assert done.metadata_path is not None and JobsRepo(db).costs(job_id)
    other = harness.submit()
    fail_job(harness.deps, other, StageName.INGEST, "boom", "boom")
    assert JobsRepo(db).get(other).status is JobStatus.FAILED  # type: ignore[union-attr]


def test_a_database_error_never_fails_the_job(tmp_path: Path) -> None:
    class Down:
        def upsert(self, summary: object) -> bool:
            raise RuntimeError("neon asleep")

        def replace_costs(self, job_id: str, costs: object) -> None:
            raise RuntimeError("neon asleep")

    harness = Harness.build(tmp_path)
    harness.deps.jobs_db = Down()  # type: ignore[assignment]
    job_id = run_channel_job(harness)
    assert harness.store.get(job_id).status is JobStatus.DONE


def test_a_costs_error_never_fails_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("dict down")

    harness = Harness.build(tmp_path)
    harness.deps.jobs_db = object()  # type: ignore[assignment]
    monkeypatch.setattr("clipforge.pipeline.steps.merged_cost", boom)
    job_id = run_channel_job(harness)
    assert harness.store.get(job_id).status is JobStatus.DONE


def test_without_a_database_costs_are_not_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("merged_cost called")

    harness = Harness.build(tmp_path)
    monkeypatch.setattr("clipforge.pipeline.steps.merged_cost", boom)
    job_id = run_channel_job(harness)
    assert harness.store.get(job_id).status is JobStatus.DONE


def test_the_job_is_saved_done_before_the_database_is_written(tmp_path: Path) -> None:
    harness = Harness.build(tmp_path)
    seen: list[JobStatus] = []

    class Spy:
        def upsert(self, summary: object) -> bool:
            job_id = summary.job_id
            seen.append(harness.store.get(job_id).status)
            raise RuntimeError("neon asleep")

        def replace_costs(self, job_id: str, costs: object) -> None:
            raise RuntimeError("neon asleep")

    harness.deps.jobs_db = Spy()  # type: ignore[assignment]
    job_id = run_channel_job(harness)
    assert JobStatus.DONE in seen  # the packaged job's upsert saw DONE already in the store
    assert harness.store.get(job_id).status is JobStatus.DONE


def test_a_failed_job_row_carries_the_cost_spent_so_far(tmp_path: Path, db: Database) -> None:
    harness = Harness.build(tmp_path)
    harness.deps.jobs_db = JobsRepo(db)
    job_id = harness.submit()
    harness.run_until(Step.HIGHLIGHTS)  # ingest and transcribe recorded their cost
    fail_job(harness.deps, job_id, StageName.HIGHLIGHTS, "boom", "boom")
    row = JobsRepo(db).get(job_id)
    assert row is not None and row.status is JobStatus.FAILED and row.cost_usd > 0
    assert JobsRepo(db).costs(job_id)


def test_resume_writes_a_running_row(tmp_path: Path, db: Database) -> None:
    harness = Harness.build(tmp_path)
    harness.deps.jobs_db = JobsRepo(db)
    job_id = harness.submit()
    fail_job(harness.deps, job_id, StageName.INGEST, "boom", "boom")
    assert JobsRepo(db).get(job_id).status is JobStatus.FAILED  # type: ignore[union-attr]
    resume(harness.deps, job_id)
    assert JobsRepo(db).get(job_id).status is JobStatus.RUNNING  # type: ignore[union-attr]


@pytest.mark.parametrize("failure", [None, RuntimeError("neon asleep")])
def test_create_job_spawns_before_the_database_is_written(
    tmp_path: Path, failure: Exception | None
) -> None:
    harness = Harness.build(tmp_path)
    order: list[str] = []
    real_spawn = harness.deps.spawner.spawn

    def spawn(step: Step, job_id: str, clip_id: str | None = None) -> None:
        order.append("spawn")
        real_spawn(step, job_id, clip_id)

    class Spy:
        def upsert(self, summary: object) -> bool:
            order.append("upsert")
            if failure:
                raise failure
            return True

        def replace_costs(self, job_id: str, costs: object) -> None:
            pass

    harness.deps.spawner.spawn = spawn  # type: ignore[method-assign]
    harness.deps.jobs_db = Spy()  # type: ignore[assignment]
    job = create_job(
        harness.deps, JobInput.model_validate({"source_url": SOURCE_URL, "permission": "own"})
    )
    assert order == ["spawn", "upsert"]
    assert harness.store.get(job.job_id).job_id == job.job_id


def test_without_a_database_failing_reads_no_costs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("merged_cost called")

    harness = Harness.build(tmp_path)
    monkeypatch.setattr("clipforge.pipeline.steps.merged_cost", boom)
    job_id = harness.submit()
    fail_job(harness.deps, job_id, StageName.INGEST, "boom", "boom")
    resume(harness.deps, job_id)
