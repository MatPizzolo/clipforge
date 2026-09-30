from datetime import timedelta

from clipforge.db.engine import Database
from clipforge.db.jobs import JobsRepo
from clipforge.models import JobInput, JobStatus, JobSummary, StageCost, StageName
from tests.dbhelpers import NOW


def _summary(status: JobStatus = JobStatus.QUEUED, at=NOW) -> JobSummary:  # type: ignore[no-untyped-def]
    return JobSummary(job_id="20260929-aaaaaaaa-0001", source_id="billy-garton", status=status,
                      input=JobInput(source_path="x.mp4", permission="own"),
                      created_at=NOW, updated_at=at)  # fmt: skip


def test_upsert_keeps_the_newest(db: Database) -> None:
    repo = JobsRepo(db)
    assert repo.upsert(_summary()) is True
    assert repo.upsert(_summary(JobStatus.DONE, NOW + timedelta(minutes=5))) is True
    assert repo.upsert(_summary(JobStatus.RUNNING, NOW + timedelta(minutes=1))) is False  # older
    assert repo.get("20260929-aaaaaaaa-0001").status is JobStatus.DONE  # type: ignore[union-attr]
    assert [s.job_id for s in repo.list()] == ["20260929-aaaaaaaa-0001"]


def test_build_round_trips(db: Database) -> None:
    repo = JobsRepo(db)
    repo.upsert(_summary().model_copy(update={"build": "abc1234"}))
    assert repo.get("20260929-aaaaaaaa-0001").build == "abc1234"  # type: ignore[union-attr]


def test_replace_costs_is_idempotent(db: Database) -> None:
    repo = JobsRepo(db)
    repo.upsert(_summary())
    costs = [StageCost(stage=StageName.TRANSCRIBE, gpu_s=12.0, usd_estimate=0.01)]
    repo.replace_costs("20260929-aaaaaaaa-0001", costs)
    repo.replace_costs("20260929-aaaaaaaa-0001", costs)
    assert repo.costs("20260929-aaaaaaaa-0001") == costs
