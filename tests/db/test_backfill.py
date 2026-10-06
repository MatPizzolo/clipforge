from pathlib import Path

from clipforge.db.backfill import backfill_jobs
from clipforge.db.engine import Database
from clipforge.db.jobs import JobsRepo
from tests.pipeline.harness import Harness
from tests.posting.builders import run_channel_job


def test_backfill_from_metadata_and_dict(tmp_path: Path, db: Database) -> None:
    harness = Harness.build(tmp_path)
    done = run_channel_job(harness)  # writes metadata.json through the fake package stage
    running = harness.submit()  # Dict only, no metadata.json
    report = backfill_jobs(harness.store.kv, tmp_path, db, dry_run=False)
    assert report.from_metadata == 1 and report.from_dict == 1 and report.written == 2
    assert JobsRepo(db).get(done).metadata_path is not None  # type: ignore[union-attr]
    assert JobsRepo(db).get(running) is not None
    assert backfill_jobs(harness.store.kv, tmp_path, db, dry_run=False).written == 0


def test_backfill_dry_run_writes_nothing(tmp_path: Path, db: Database) -> None:
    harness = Harness.build(tmp_path)
    done = run_channel_job(harness)
    report = backfill_jobs(harness.store.kv, tmp_path, db, dry_run=True)
    assert report.dry_run and report.from_metadata == 1 and report.written == 0
    assert JobsRepo(db).get(done) is None
