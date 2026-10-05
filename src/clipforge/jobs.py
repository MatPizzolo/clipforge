"""Job state, progress, cost and stage caching (ADR-8, ADR-14).

`DictJobStore` keeps each job in single-writer keys of a `KV` (a modal.Dict in production,
`MemoryKV` in tests). Stages get a `JobContext` and call `ctx.report(...)` and
`ctx.record_cost(...)`; in a clip step the context writes that clip's key, not the job's.
"""

from __future__ import annotations

import hashlib
import logging
import re
import secrets
import shutil
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ValidationError

from clipforge.models import ClipState, CostSummary, Job, Progress, StageCost, StageName
from clipforge.pipeline.deps import KV

log = logging.getLogger(__name__)

CACHE_DIR = "cache"
RESULT_FILE = "result.json"


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_job_id(seed: str, now: datetime | None = None) -> str:
    """`<yyyymmdd>-<hash8 of seed>-<rand4>`; seed is the source URL, file id or path."""
    day = (now or utcnow()).strftime("%Y%m%d")
    digest = hashlib.sha256(seed.encode()).hexdigest()[:8]
    return f"{day}-{digest}-{secrets.token_hex(2)}"


_JOB_ID = re.compile(r"\d{8}-[0-9a-f]{8}-[0-9a-f]{4}")


def is_job_id(value: str) -> bool:
    """True for ids `new_job_id` makes; anything else (paths, `..`) is rejected at the edge."""
    return _JOB_ID.fullmatch(value) is not None


class DictJobStore:
    """Job state in single-writer KV keys (ADR-14). Values are JSON strings."""

    def __init__(self, kv: KV) -> None:
        self.kv = kv

    @staticmethod
    def _job_key(job_id: str) -> str:
        return f"job:{job_id}"

    @staticmethod
    def _clip_key(job_id: str, clip_id: str) -> str:
        return f"job:{job_id}:clip:{clip_id}"

    @staticmethod
    def _attempts_key(job_id: str, step: str, clip_id: str | None) -> str:
        suffix = f":{clip_id}" if clip_id else ""
        return f"job:{job_id}:attempts:{step}{suffix}"

    @staticmethod
    def _claim_key(job_id: str, name: str) -> str:
        return f"job:{job_id}:claim:{name}"

    # ---- core job record

    def save(self, job: Job) -> None:
        self.kv.put(self._job_key(job.job_id), job.model_dump_json())

    def get(self, job_id: str) -> Job:
        raw = self.kv.get(self._job_key(job_id))
        if raw is None:
            raise KeyError(f"unknown job {job_id!r}")
        return Job.model_validate_json(raw)

    def list_job_ids(self) -> list[str]:
        return [
            key.removeprefix("job:")
            for key in self.kv.keys()  # noqa: SIM118 (KV is a protocol, not a dict)
            if key.startswith("job:") and key.count(":") == 1
        ]

    def job_records(self) -> list[tuple[str, str]]:
        """Every core record as (job id, raw JSON), in one streaming read instead of one `get`
        per job (the posting overview, card 039)."""
        return [
            (key.removeprefix("job:"), value)
            for key, value in self.kv.items()
            if key.startswith("job:") and key.count(":") == 1
        ]

    # ---- clip records

    def create_clip(self, job_id: str, state: ClipState) -> bool:
        """Set-if-absent, so a retried highlights step never resets a clip in progress."""
        key = self._clip_key(job_id, state.clip_id)
        return self.kv.put(key, state.model_dump_json(), skip_if_exists=True)

    def save_clip(self, job_id: str, state: ClipState) -> None:
        self.kv.put(self._clip_key(job_id, state.clip_id), state.model_dump_json())

    def get_clip(self, job_id: str, clip_id: str) -> ClipState:
        raw = self.kv.get(self._clip_key(job_id, clip_id))
        if raw is None:
            raise KeyError(f"unknown clip {job_id!r}/{clip_id!r}")
        return ClipState.model_validate_json(raw)

    def clips(self, job_id: str, clip_ids: list[str]) -> list[ClipState]:
        return [self.get_clip(job_id, clip_id) for clip_id in clip_ids]

    # ---- attempts and claims

    def incr_attempts(self, job_id: str, step: str, clip_id: str | None = None) -> int:
        key = self._attempts_key(job_id, step, clip_id)
        count = int(self.kv.get(key) or 0) + 1
        self.kv.put(key, str(count))
        return count

    def reset_attempts(self, job_id: str) -> None:
        prefix = f"job:{job_id}:attempts:"
        for key in list(self.kv.keys()):
            if key.startswith(prefix):
                self.kv.delete(key)

    def claim(self, job_id: str, name: str) -> bool:
        """Atomic: True for exactly one caller until released."""
        return self.kv.put(self._claim_key(job_id, name), "1", skip_if_exists=True)

    def release(self, job_id: str, name: str) -> None:
        self.kv.delete(self._claim_key(job_id, name))

    def release_all(self, job_id: str, name_prefix: str) -> None:
        """Release every claim whose name starts with `name_prefix` (e.g. "spawn:")."""
        prefix = self._claim_key(job_id, name_prefix)
        for key in list(self.kv.keys()):
            if key.startswith(prefix):
                self.kv.delete(key)

    def claim_update(self, update_id: int) -> bool:
        """Telegram redelivers webhooks; each update is handled once (`tg:update:<id>`)."""
        return self.kv.put(f"tg:update:{update_id}", "1", skip_if_exists=True)


@dataclass
class JobContext:
    """Everything a stage needs besides its input: where files go and where progress goes."""

    job_id: str
    root: Path  # JOBS_ROOT; contract paths are relative to it
    store: DictJobStore
    clip_id: str | None = None  # set in clip steps: progress and cost go to the clip's key
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def job_dir(self) -> Path:
        return self.root / self.job_id

    def path(self, rel: str) -> Path:
        """Resolve a contract path (relative to JOBS_ROOT)."""
        return self.root / rel

    def rel(self, path: Path) -> str:
        """Turn an absolute path under JOBS_ROOT into a contract path."""
        return path.resolve().relative_to(self.root.resolve()).as_posix()

    def job(self) -> Job:
        return self.store.get(self.job_id)

    def _update_job(self, change: Callable[[Job], Job]) -> None:
        with self._lock:
            job = change(self.store.get(self.job_id))
            self.store.save(job.model_copy(update={"updated_at": utcnow()}))

    def _update_clip(self, clip_id: str, change: Callable[[ClipState], ClipState]) -> None:
        with self._lock:
            state = change(self.store.get_clip(self.job_id, clip_id))
            self.store.save_clip(self.job_id, state.model_copy(update={"updated_at": utcnow()}))

    def report(self, stage: StageName, pct: float, message: str = "") -> None:
        """Record progress for a long-running stage (CLAUDE.md rule 3)."""
        progress = Progress(
            stage=stage, pct=max(0.0, min(100.0, pct)), message=message, at=utcnow()
        )
        if self.clip_id is None:
            self._update_job(lambda job: job.model_copy(update={"progress": progress}))
        else:
            self._update_clip(self.clip_id, lambda s: s.model_copy(update={"progress": progress}))

    def record_cost(self, cost: StageCost) -> None:
        """Append a cost entry (CLAUDE.md rule 7); clip contexts tag it with the clip id."""
        if self.clip_id is None:
            self._update_job(
                lambda job: job.model_copy(
                    update={"cost": CostSummary(stages=[*job.cost.stages, cost])}
                )
            )
        else:
            tagged = cost.model_copy(update={"clip_id": self.clip_id})
            self._update_clip(
                self.clip_id, lambda s: s.model_copy(update={"cost": [*s.cost, tagged]})
            )


@dataclass(frozen=True)
class Stored[T: BaseModel]:
    """A stage output and the ref of its result.json (relative to JOBS_ROOT)."""

    value: T
    ref: str


def load_ref[T: BaseModel](root: Path, ref: str, model: type[T]) -> T:
    return model.model_validate_json((root / ref).read_text())


def cached_stage[T: BaseModel](
    ctx: JobContext,
    stage: StageName,
    key: str,
    output_type: type[T],
    compute: Callable[[Path], T],
    clip_id: str | None = None,
) -> Stored[T]:
    """Return the cached output for `key`, or run `compute(out_dir)` and cache its result.

    `compute` writes its files into `out_dir` (`<JOBS_ROOT>/cache/<stage>/<key>/`) and returns
    the output contract; `result.json` is written last and marks the entry complete. A missing
    or invalid `result.json` (crash mid-stage, contract changed) is a cache miss.
    """
    ref = f"{CACHE_DIR}/{stage.value}/{key}/{RESULT_FILE}"
    result_file = ctx.root / ref
    out_dir = result_file.parent
    if result_file.exists():
        try:
            result = output_type.model_validate_json(result_file.read_text())
        except ValidationError:
            log.warning("cached %s output %s no longer validates; recomputing", stage, key)
        else:
            ctx.record_cost(StageCost(stage=stage, clip_id=clip_id, cached=True))
            return Stored(result, ref)

    if out_dir.exists():
        shutil.rmtree(out_dir)  # leftovers from an interrupted run
    out_dir.mkdir(parents=True)
    result = compute(out_dir)
    tmp = result_file.with_suffix(".tmp")
    tmp.write_text(result.model_dump_json(indent=2))
    tmp.replace(result_file)
    return Stored(result, ref)


def merged_cost(store: DictJobStore, job: Job) -> CostSummary:
    """The job's cost entries plus every clip's (ADR-14 keeps them in separate keys)."""
    clips = store.clips(job.job_id, job.clip_ids)
    return CostSummary(stages=[*job.cost.stages, *(entry for c in clips for entry in c.cost)])
