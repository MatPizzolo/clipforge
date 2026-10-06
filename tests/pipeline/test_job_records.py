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


def test_done_wins_over_a_newer_queued_row_when_the_clock_steps_back(
    tmp_path: Path, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    # card 017 item 9 / log #143: the WSL clock steps back by up to 1.4 s, and the `updated_at`
    # guard used to drop the package step's DONE write, leaving the row `queued`
    from datetime import timedelta

    from clipforge.jobs import utcnow

    harness = Harness.build(tmp_path)
    harness.deps.jobs_db = JobsRepo(db)
    job_input = JobInput.model_validate(
        {"source_url": SOURCE_URL, "permission": "own", "options": {"n": 2}}
    )
    job_id = create_job(harness.deps, job_input).job_id
    monkeypatch.setattr("clipforge.pipeline.steps.utcnow", lambda: utcnow() - timedelta(seconds=2))
    harness.run()
    row = JobsRepo(db).get(job_id)
    assert row is not None and row.status is JobStatus.DONE


def test_upsert_keeps_a_terminal_row_over_an_older_running_write(db: Database) -> None:
    from datetime import UTC, datetime, timedelta

    from clipforge.models import JobSummary

    t = datetime(2026, 10, 5, 12, tzinfo=UTC)
    job_input = JobInput.model_validate({"source_url": SOURCE_URL, "permission": "own"})
    base = JobSummary(job_id="20261005-aaaaaaaa-0001", source_id=None, status=JobStatus.QUEUED,
                      input=job_input, created_at=t, updated_at=t)  # fmt: skip
    repo = JobsRepo(db)
    assert repo.upsert(base.model_copy(update={"updated_at": t + timedelta(seconds=5)}))
    # a terminal write stamped earlier than the queued row still lands
    assert repo.upsert(base.model_copy(update={"status": JobStatus.DONE}))
    # an older non-terminal write never replaces a terminal row
    assert not repo.upsert(
        base.model_copy(
            update={"status": JobStatus.RUNNING, "updated_at": t - timedelta(seconds=1)}
        )
    )
    got = repo.get(base.job_id)
    assert got is not None and got.status is JobStatus.DONE
    # a newer non-terminal write (resume) still replaces it
    assert repo.upsert(
        base.model_copy(
            update={"status": JobStatus.RUNNING, "updated_at": t + timedelta(seconds=9)}
        )
    )


def test_a_stale_terminal_write_never_replaces_a_newer_resume(db: Database) -> None:
    # PR review: terminal-wins is only for clock skew, not for a failure from before a resume
    from datetime import UTC, datetime, timedelta

    from clipforge.models import JobSummary

    t = datetime(2026, 10, 5, 12, tzinfo=UTC)
    job_input = JobInput.model_validate({"source_url": SOURCE_URL, "permission": "own"})
    resumed = t + timedelta(minutes=5)
    base = JobSummary(job_id="20261005-aaaaaaaa-0002", source_id=None, status=JobStatus.RUNNING,
                      input=job_input, created_at=t, updated_at=resumed)  # fmt: skip
    repo = JobsRepo(db)
    assert repo.upsert(base)  # resumed at t + 5 min
    stale = base.model_copy(update={"status": JobStatus.FAILED, "updated_at": t})
    assert not repo.upsert(stale)
    got = repo.get(base.job_id)
    assert got is not None and got.status is JobStatus.RUNNING
