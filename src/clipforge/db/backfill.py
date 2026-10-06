"""`posting_daily`'s jobs backfill (ADR-46): writes a `jobs` row for every finished job whose
row is missing or older, from `metadata.json` on the Volume, then from the Dict's `job:*`
records the Volume lacks. Idempotent. It was `clipforge jobs backfill` until S1 Task 23
(card 040), which removed the route and kept the daily part. Modal-free."""

from __future__ import annotations

import logging
from pathlib import Path

from clipforge.db.engine import Database, redact
from clipforge.db.jobs import JobsRepo
from clipforge.jobs import DictJobStore
from clipforge.models import BackfillReport, JobMetadata, JobStatus, JobSummary, StageCost
from clipforge.pipeline.deps import KV
from clipforge.pipeline.steps import summary_of

log = logging.getLogger(__name__)


def summary_from_metadata(
    meta: JobMetadata, metadata_path: str, costs: list[StageCost]
) -> JobSummary:
    return JobSummary(
        job_id=meta.job_id, source_id=meta.input.channel.slug if meta.input.channel else None,
        status=JobStatus.DONE, source_label=meta.input.source_label, input=meta.input,
        created_at=meta.started_at, updated_at=meta.finished_at, finished_at=meta.finished_at,
        cost_usd=sum(c.usd_estimate for c in costs), metadata_path=metadata_path,
    )  # fmt: skip


def _stale(repo: JobsRepo, summary: JobSummary) -> bool:
    """True when the row is missing or older, so a re-run writes nothing (upsert alone would
    rewrite an equal timestamp)."""
    have = repo.get(summary.job_id)
    return (
        have is None
        or have.updated_at < summary.updated_at
        or (summary.metadata_path is not None and have.metadata_path != summary.metadata_path)
    )


def backfill_jobs(kv: KV, root: Path, db: Database, dry_run: bool) -> BackfillReport:
    repo = JobsRepo(db)
    from_metadata = from_dict = written = 0
    failed: list[str] = []
    seen: set[str] = set()
    for path in sorted(root.glob("*/output/metadata.json")):
        try:
            meta = JobMetadata.model_validate_json(path.read_text())
            seen.add(meta.job_id)
            from_metadata += 1
            costs: list[StageCost] = list(meta.cost.stages)
            summary = summary_from_metadata(meta, str(path.relative_to(root)), costs)
            if not dry_run and _stale(repo, summary) and repo.upsert(summary):
                repo.replace_costs(meta.job_id, costs)
                written += 1
        except Exception as exc:
            log.warning("backfill: %s failed: %s", path.parent.parent.name, redact(exc))
            failed.append(path.parent.parent.name)
    store = DictJobStore(kv)
    for job_id in store.list_job_ids():
        if job_id in seen:
            continue
        try:
            job = store.get(job_id)
            from_dict += 1
            summary = summary_of(job)
            if not dry_run and _stale(repo, summary) and repo.upsert(summary):
                written += 1
        except Exception as exc:
            log.warning("backfill: %s failed: %s", job_id, redact(exc))
            failed.append(job_id)
    return BackfillReport(dry_run=dry_run, from_metadata=from_metadata, from_dict=from_dict,
                          written=written, failed=failed)  # fmt: skip
