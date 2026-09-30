"""One-off move of the ADR-23 Dict queue and job records to Postgres, plus the check that both
stores agree (spec §5.5). Reads the Dict, never writes it. Removed with the Dict writes
(spec §9.3)."""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel, ValidationError

from clipforge.db.accounts import AccountsRepo
from clipforge.db.engine import Database, redact
from clipforge.db.jobs import JobsRepo
from clipforge.db.posting import SqlPostingRepo
from clipforge.db.sources import SourcesRepo
from clipforge.jobs import DictJobStore, utcnow
from clipforge.models import (
    AssetSource,
    BackfillReport,
    ImportReport,
    JobMetadata,
    JobStatus,
    JobSummary,
    PostItem,
    PostMark,
    PostRecord,
    PostSend,
    PostStatus,
    PostVerdict,
    StageCost,
    VerifyReport,
)
from clipforge.pipeline.deps import KV, MemoryKV
from clipforge.pipeline.steps import summary_of
from clipforge.posting import queue
from clipforge.posting.keepalive import newest_snapshot
from clipforge.posting.repo import PAUSED_KEY, PREFIX, DictPostingRepo

log = logging.getLogger(__name__)

_MODELS: dict[str, type[BaseModel]] = {
    "item": PostItem, "sent": PostSend, "posted": PostMark, "verdict": PostVerdict,
}  # fmt: skip


def _dict_records(kv: KV, root: Path, account_id: str) -> tuple[list[PostRecord], int, list[str]]:
    """Every record the Dict holds, plus, for items whose base key expired from the Dict, the
    keys of the newest snapshot. An item still in the Dict is never topped up from the
    snapshot: a missing `posted:<platform>` there is an untick, not an expiry. Keys that
    don't validate are returned by key. Built in a scratch KV, so the Dict is only read."""
    values = {k: v for k, v in kv.items() if k.startswith(PREFIX)}
    live = {k for k in values if k.count(":") == 2}
    filled = 0
    for key, value in (newest_snapshot(root) or {}).items():
        base = ":".join(key.split(":")[:3])
        if (
            key.startswith(PREFIX)
            and base not in live
            and key not in values
            and isinstance(value, str)
        ):
            values[key] = value
            filled += 1
    bad: list[str] = []
    for key, raw in values.items():
        parts = key.split(":")
        kind = parts[3] if len(parts) > 3 else "item"
        model = _MODELS.get(kind)
        if model is not None:
            try:
                model.model_validate_json(raw)
            except ValidationError:
                bad.append(key)
    staged = MemoryKV()
    for key, value in values.items():
        staged.put(key, value)
    return DictPostingRepo(staged, account_id).records(account_id), filled, bad


def import_posting(
    kv: KV, root: Path, db: Database, account_id: str, dry_run: bool
) -> ImportReport:
    records, filled, invalid = _dict_records(kv, root, account_id)
    sources, accounts, sql = SourcesRepo(db), AccountsRepo(db), SqlPostingRepo(db)
    by_status: dict[PostStatus, int] = {}
    imported = already = 0
    missing: list[str] = []
    failed: list[str] = list(invalid)
    for record in records:
        state = queue.status(record)
        by_status[state] = by_status.get(state, 0) + 1
        try:
            source = sources.get(record.item.source_id or "")
            if source is None:
                missing.append(record.item.id)
                continue
            account = accounts.get(source.account_id)
            item = record.item.model_copy(update={
                "account_id": source.account_id,
                "language": account.language if account else record.item.language,
                "assets": [AssetSource(kind="source_video", license=source.permission.type.value,
                                       attribution=source.credit_name,
                                       url=str(source.url) if source.url else None)],
            })  # fmt: skip
            record = record.model_copy(update={"item": item})
            if sql.get(item.id) is not None:
                already += 1
            elif dry_run or sql.import_record(record, account.posting.chat_id if account else None):
                imported += 1
            else:
                already += 1
        except Exception as exc:
            log.warning("import: %s failed: %s", record.item.id, redact(exc))
            failed.append(record.item.id)
    paused = kv.get(PAUSED_KEY) is not None
    if paused and not dry_run:
        try:
            accounts.set_paused(account_id, True, utcnow())
        except Exception as exc:
            log.warning("import: pausing %s failed: %s", account_id, redact(exc))
            failed.append(f"paused:{account_id}")
    return ImportReport(dry_run=dry_run, dict_items=len(records), from_snapshot=filled,
                        by_status=by_status, imported=imported, already=already,
                        missing_source=missing, failed=failed, paused=paused)  # fmt: skip


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


def _key(record: PostRecord) -> tuple[object, ...]:
    verdict = record.verdict
    return (
        queue.status(record).value,
        record.unavailable,
        tuple((x.n, x.at, x.slot, x.message_id, x.video_message_id) for x in record.sends),
        tuple(sorted((p.value, at) for p, at in record.posted.items())),
        (verdict.kind, verdict.at, verdict.reason) if verdict else None,
    )


def verify_posting(kv: KV, db: Database, account_id: str) -> VerifyReport:
    dict_repo, sql = DictPostingRepo(kv, account_id), SqlPostingRepo(db)
    left = {r.item.id: r for r in dict_repo.records(account_id)}
    right = {r.item.id: r for r in sql.records(account_id)}
    diffs: list[str] = []
    if dict_repo.paused(account_id) != sql.paused(account_id):
        diffs.append(
            f"paused: dict={dict_repo.paused(account_id)} postgres={sql.paused(account_id)}"
        )
    for ref in sorted(set(left) | set(right)):
        if ref not in right:
            diffs.append(f"{ref}: only in the Dict")
        elif ref not in left:
            diffs.append(f"{ref}: only in Postgres")
        elif _key(left[ref]) != _key(right[ref]):
            diffs.append(f"{ref}: dict={_key(left[ref])} postgres={_key(right[ref])}")
    return VerifyReport(account_id=account_id, dict_items=len(left), postgres_items=len(right),
                        differences=len(diffs), first=diffs[:50])  # fmt: skip
