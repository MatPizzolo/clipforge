"""Job summaries and per-stage costs (spec §3): the durable mirror of `job:*` (ADR-26)."""

from __future__ import annotations

import builtins
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from clipforge.db.engine import Database
from clipforge.db.tables import costs, jobs
from clipforge.models import JobSummary, StageCost, StageName

_COST_FIELDS = ("wall_s", "gpu_s", "gpu_type", "llm_model", "llm_input_tokens",
                "llm_output_tokens", "llm_calls", "cached")  # fmt: skip


def _summary(row: Any) -> JobSummary:
    return JobSummary.model_validate(dict(row._mapping))


class JobsRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def upsert(self, summary: JobSummary) -> bool:
        values = summary.model_dump(mode="json")
        statement = insert(jobs).values(**values)
        upsert = statement.on_conflict_do_update(
            index_elements=[jobs.c.job_id],
            set_={k: statement.excluded[k] for k in values if k != "job_id"},
            where=jobs.c.updated_at <= statement.excluded.updated_at,
        ).returning(jobs.c.job_id)
        with self.db.begin() as conn:
            return conn.execute(upsert).first() is not None

    def get(self, job_id: str) -> JobSummary | None:
        with self.db.begin() as conn:
            row = conn.execute(select(jobs).where(jobs.c.job_id == job_id)).first()
        return None if row is None else _summary(row)

    def list(self) -> builtins.list[JobSummary]:
        with self.db.begin() as conn:
            return [_summary(r) for r in conn.execute(select(jobs).order_by(jobs.c.job_id))]

    def replace_costs(self, job_id: str, stage_costs: builtins.list[StageCost]) -> None:
        with self.db.begin() as conn:
            conn.execute(costs.delete().where(costs.c.job_id == job_id))
            if stage_costs:
                conn.execute(costs.insert(), [{
                    "job_id": job_id, "stage": c.stage.value, "clip_id": c.clip_id,
                    "usd": c.usd_estimate, **{f: getattr(c, f) for f in _COST_FIELDS},
                } for c in stage_costs])  # fmt: skip

    def costs(self, job_id: str) -> builtins.list[StageCost]:
        with self.db.begin() as conn:
            rows = conn.execute(select(costs).where(costs.c.job_id == job_id).order_by(costs.c.id))
            return [StageCost(stage=StageName(r.stage), clip_id=r.clip_id, usd_estimate=r.usd,
                              **{f: getattr(r, f) for f in _COST_FIELDS}) for r in rows]  # fmt: skip  # noqa: E501
