"""The step chain (ADR-12): one function per Modal step. Modal-free.

Each step reloads the Volume, loads the job, runs its stage (cached, ADR-8), commits the
Volume, records the output ref and spawns the next step. Errors follow ADR-15:
`PermanentError` fails at once; other exceptions are re-raised for Modal to retry until
`max_attempts`, then fail cleanly.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel

from clipforge.jobs import DictJobStore, JobContext, load_ref, merged_cost, utcnow
from clipforge.models import (
    ClipSpec,
    ClipState,
    ClipStatus,
    Job,
    JobError,
    JobStatus,
    JobSummary,
    RenderedClip,
    SourceMedia,
    StageCost,
    StageName,
    Transcript,
)
from clipforge.pipeline.deps import (
    Notifier,
    NullNotifier,
    SafeNotifier,
    Spawner,
    StageRunner,
    Volume,
)
from clipforge.pipeline.errors import PermanentError
from clipforge.pipeline.selection import select_clips
from clipforge.posting.enqueue import ClipFacts, enqueue_job
from clipforge.sanitize import clean, redact

if TYPE_CHECKING:
    from clipforge.db.jobs import JobsRepo
    from clipforge.ops import OpsAlerts
    from clipforge.posting.backend import Posting

log = logging.getLogger(__name__)


class Step(StrEnum):
    INGEST = "ingest"
    TRANSCRIBE = "transcribe"
    HIGHLIGHTS = "highlights"
    CLIP = "clip"
    PACKAGE = "package"


# Modal function timeouts (app.py uses these) and the sweeper's stall margin (ADR-15).
STEP_TIMEOUT_S: dict[Step, int] = {
    Step.INGEST: 15 * 60,
    Step.TRANSCRIBE: 30 * 60,
    Step.HIGHLIGHTS: 10 * 60,
    Step.CLIP: 10 * 60,
    Step.PACKAGE: 10 * 60,
}
STALL_MARGIN_S = 5 * 60
MAX_ATTEMPTS = 3  # first try + Modal Retries(max_retries=2)

# The stage a step's failures are reported under.
STEP_STAGE: dict[Step, StageName] = {
    Step.INGEST: StageName.INGEST,
    Step.TRANSCRIBE: StageName.TRANSCRIBE,
    Step.HIGHLIGHTS: StageName.HIGHLIGHTS,
    Step.CLIP: StageName.RENDER,
    Step.PACKAGE: StageName.PACKAGE,
}

sanitize = clean  # user-facing error text (see clipforge.sanitize)


def _no_notifier(job: Job) -> Notifier:
    return NullNotifier()


@dataclass
class Deps:
    store: DictJobStore
    volume: Volume
    spawner: Spawner
    stages: StageRunner
    root: Path  # JOBS_ROOT
    notifier_for: Callable[[Job], Notifier] = _no_notifier
    max_attempts: int = MAX_ATTEMPTS
    posting: Posting | None = None
    jobs_db: JobsRepo | None = None
    version: str = "clips:unknown"  # producer version on new items (ADR-43), not the git SHA
    build: str | None = None  # the deploy's git SHA, kept on job rows
    ops: OpsAlerts | None = None  # silent failures to the owner's chat (ADR-45)

    def notifier(self, job: Job) -> Notifier:
        """Never raises: a broken notifier must not fail or retry a step (ADR-14)."""
        try:
            inner = self.notifier_for(job)
        except Exception:
            log.exception("building the notifier failed for %s", job.job_id)
            inner = NullNotifier()
        return SafeNotifier(inner)

    def context(self, job_id: str, clip_id: str | None = None) -> JobContext:
        return JobContext(job_id=job_id, root=self.root, store=self.store, clip_id=clip_id)


# ---- helpers


def _set(job: Job, **changes: object) -> Job:
    return job.model_copy(update={**changes, "updated_at": utcnow()})


def _set_clip(state: ClipState, **changes: object) -> ClipState:
    return state.model_copy(update={**changes, "updated_at": utcnow()})


def _start(deps: Deps, job_id: str, stage: StageName) -> None:
    deps.store.save(_set(deps.store.get(job_id), status=JobStatus.RUNNING, stage=stage))


def _handoff(deps: Deps, job_id: str, next_step: Step, clip_ids: list[str] | None = None) -> None:
    """Spawn the next step (or every clip step) at most once per job, even when this step
    runs twice. If spawning raises, the claim is released so the retry spawns instead."""
    if not deps.store.claim(job_id, f"spawn:{next_step}"):
        return
    try:
        if clip_ids is None:
            deps.spawner.spawn(next_step, job_id)
        else:
            for clip_id in clip_ids:
                deps.spawner.spawn(next_step, job_id, clip_id)
    except Exception:
        deps.store.release(job_id, f"spawn:{next_step}")
        raise


def _advance(deps: Deps, job_id: str, stage: StageName, ref: str, next_step: Step) -> None:
    """Commit files, record the output ref, then hand over to the next step."""
    deps.volume.commit()
    job = deps.store.get(job_id)
    deps.store.save(_set(job, outputs={**job.outputs, stage: ref}))
    _handoff(deps, job_id, next_step)


def _output[T: BaseModel](deps: Deps, job: Job, stage: StageName, model: type[T]) -> T:
    ref = job.outputs.get(stage)
    if ref is None:
        raise RuntimeError(f"job {job.job_id} has no {stage} output yet")
    return load_ref(deps.root, ref, model)


def _write_json(deps: Deps, rel: str, model: BaseModel) -> None:
    path = deps.root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(model.model_dump_json(indent=2))


# ---- failure handling (ADR-15)


def summary_of(
    job: Job,
    *,
    costs: list[StageCost] | None = None,
    metadata_path: str | None = None,
    build: str | None = None,
) -> JobSummary:
    finished = job.updated_at if job.status in (JobStatus.DONE, JobStatus.FAILED) else None
    return JobSummary(
        job_id=job.job_id, source_id=job.input.channel.slug if job.input.channel else None,
        status=job.status, source_label=job.input.source_label, input=job.input,
        created_at=job.created_at, updated_at=job.updated_at, finished_at=finished,
        cost_usd=sum(c.usd_estimate for c in costs or []), metadata_path=metadata_path,
        build=build,
    )  # fmt: skip


def record_job(
    deps: Deps, job: Job, *, costs: list[StageCost] | None = None, metadata_path: str | None = None
) -> None:
    """Best-effort durable row (spec §7): metadata.json stays the record, and `jobs backfill`
    repairs a missed write, so a database error never fails or retries a step."""
    if deps.jobs_db is None:
        return
    try:
        deps.jobs_db.upsert(
            summary_of(job, costs=costs, metadata_path=metadata_path, build=deps.build)
        )
        if costs is not None:
            deps.jobs_db.replace_costs(job.job_id, costs)
    except Exception as exc:
        log.warning("recording job %s failed: %s", job.job_id, redact(exc))


def record_job_with_costs(deps: Deps, job: Job, metadata_path: str | None = None) -> None:
    """record_job with the merged costs, computed only when a database is wired and inside the
    guard, so a Dict error here never fails package after the zip link was sent."""
    if deps.jobs_db is None:
        return
    try:
        costs = merged_cost(deps.store, job).stages
    except Exception as exc:
        log.warning("reading costs of %s failed: %s", job.job_id, redact(exc))
        return
    record_job(deps, job, costs=costs, metadata_path=metadata_path)


def fail_job(deps: Deps, job_id: str, stage: StageName, error_type: str, message: str) -> bool:
    """Mark the job failed, and notify once. Returns True for the caller that notified.

    The status is written even when the claim is already held: an earlier caller may have
    crashed between claiming and writing, and the job must not stay `running` forever.
    """
    first = deps.store.claim(job_id, "failed")
    job = deps.store.get(job_id)
    if job.status is not JobStatus.FAILED:
        error = JobError(stage=stage, error_type=error_type, message=sanitize(message))
        job = _set(job, status=JobStatus.FAILED, error=error)
        deps.store.save(job)
        record_job_with_costs(deps, job)
    if first:
        deps.notifier(job).failed(job)
        if job.input.notify is None and deps.ops is not None:
            # channel and CLI jobs have no Telegram notifier: without this the failure is silent
            recorded = job.error
            where = recorded.stage if recorded else stage
            what = recorded.message if recorded else message
            deps.ops.alert(f"Job {job_id} failed at {where}: {what}\n/resume {job_id}",
                           "job_failed", job_id, path=f"/jobs/{job_id}")  # fmt: skip
    return first


def _fail_clip(deps: Deps, job_id: str, clip_id: str, error_type: str, message: str) -> None:
    state = deps.store.get_clip(job_id, clip_id)
    stage = state.progress.stage if state.progress else StageName.RENDER
    error = JobError(stage=stage, error_type=error_type, message=sanitize(message))
    deps.store.save_clip(job_id, _set_clip(state, status=ClipStatus.FAILED, error=error))
    _maybe_package(deps, job_id)


def _maybe_package(deps: Deps, job_id: str) -> None:
    """Fan-in: the first caller to see every clip finished spawns package (ADR-12)."""
    job = deps.store.get(job_id)
    clips = deps.store.clips(job_id, job.clip_ids)
    if clips and all(c.finished for c in clips) and deps.store.claim(job_id, "package"):
        deps.spawner.spawn(Step.PACKAGE, job_id)


def _guarded(
    deps: Deps,
    step: Step,
    job_id: str,
    body: Callable[[Job], None],
    clip_id: str | None = None,
) -> None:
    deps.volume.reload()
    try:
        job = deps.store.get(job_id)
    except KeyError:
        log.warning("%s step for unknown job %s; ignoring", step, job_id)
        return
    if job.status in (JobStatus.DONE, JobStatus.FAILED):
        log.info("%s step for %s job %s; ignoring", step, job.status, job_id)
        return
    attempt = deps.store.incr_attempts(job_id, step, clip_id)
    try:
        body(job)
    except PermanentError as exc:
        _handle_failure(deps, step, job_id, "permanent", exc.user_message, clip_id)
    except Exception as exc:
        if attempt < deps.max_attempts:
            log.warning(
                "%s step attempt %d/%d failed for %s",
                step, attempt, deps.max_attempts, job_id, exc_info=True,
            )  # fmt: skip
            raise
        log.exception("%s step failed for %s after %d attempts", step, job_id, attempt)
        name = type(exc).__name__
        _handle_failure(deps, step, job_id, name, f"{name}: {exc}", clip_id)


def _handle_failure(
    deps: Deps, step: Step, job_id: str, error_type: str, message: str, clip_id: str | None
) -> None:
    if clip_id is not None:
        _fail_clip(deps, job_id, clip_id, error_type, message)
    else:
        fail_job(deps, job_id, STEP_STAGE[step], error_type, message)


# ---- steps


def ingest_step(deps: Deps, job_id: str) -> None:
    def body(job: Job) -> None:
        if StageName.INGEST in job.outputs:  # late or duplicate delivery
            _handoff(deps, job_id, Step.TRANSCRIBE)
            return
        _start(deps, job_id, StageName.INGEST)
        stored = deps.stages.ingest(deps.context(job_id), job.input)
        _advance(deps, job_id, StageName.INGEST, stored.ref, Step.TRANSCRIBE)

    _guarded(deps, Step.INGEST, job_id, body)


def transcribe_step(deps: Deps, job_id: str) -> None:
    def body(job: Job) -> None:
        if StageName.TRANSCRIBE in job.outputs:  # late or duplicate delivery
            _handoff(deps, job_id, Step.HIGHLIGHTS)
            return
        source = _output(deps, job, StageName.INGEST, SourceMedia)
        _start(deps, job_id, StageName.TRANSCRIBE)
        stored = deps.stages.transcribe(deps.context(job_id), source)
        _advance(deps, job_id, StageName.TRANSCRIBE, stored.ref, Step.HIGHLIGHTS)

    _guarded(deps, Step.TRANSCRIBE, job_id, body)


def highlights_step(deps: Deps, job_id: str) -> None:
    def body(job: Job) -> None:
        if StageName.HIGHLIGHTS in job.outputs:  # late or duplicate delivery
            _handoff(deps, job_id, Step.CLIP, job.clip_ids)
            return
        source = _output(deps, job, StageName.INGEST, SourceMedia)
        transcript = _output(deps, job, StageName.TRANSCRIBE, Transcript)
        _start(deps, job_id, StageName.HIGHLIGHTS)
        options = job.input.options
        stored = deps.stages.highlights(deps.context(job_id), transcript, options)
        specs = select_clips(stored.value, source, options)
        if not specs and options.n is None and stored.value.candidates:
            best = stored.value.candidates[0].score
            raise PermanentError(
                f"no clip scored {options.min_score:.2f} or higher (the best was {best:.2f}); "
                "try --min-score 0.7 (Telegram: score=0.7) or --n 3"
            )
        if not specs:
            raise PermanentError("no clip-worthy segments found in this video")

        spec_refs = {spec.clip_id: f"{job_id}/clips/{spec.clip_id}.json" for spec in specs}
        for spec in specs:
            _write_json(deps, spec_refs[spec.clip_id], spec)
        deps.volume.commit()

        now = utcnow()
        for clip_id, ref in spec_refs.items():
            deps.store.create_clip(job_id, ClipState(clip_id=clip_id, spec_ref=ref, updated_at=now))
        job = deps.store.get(job_id)
        deps.store.save(
            _set(
                job,
                stage=StageName.RENDER,
                outputs={**job.outputs, StageName.HIGHLIGHTS: stored.ref},
                clip_ids=list(spec_refs),
            )
        )
        _handoff(deps, job_id, Step.CLIP, list(spec_refs))

    _guarded(deps, Step.HIGHLIGHTS, job_id, body)


def clip_step(deps: Deps, job_id: str, clip_id: str) -> None:
    def body(job: Job) -> None:
        state = deps.store.get_clip(job_id, clip_id)
        if state.status is ClipStatus.DONE:  # retry after a crash, or a duplicate spawn
            if not state.telegram_sent and state.result_ref is not None:
                _deliver(deps, job, state, load_ref(deps.root, state.result_ref, RenderedClip))
            _maybe_package(deps, job_id)
            return
        spec = load_ref(deps.root, state.spec_ref, ClipSpec)
        transcript = _output(deps, job, StageName.TRANSCRIBE, Transcript)
        deps.store.save_clip(job_id, _set_clip(state, status=ClipStatus.RUNNING, error=None))

        stored = deps.stages.clip(deps.context(job_id, clip_id), spec, transcript)
        # The cached render may come from another job with a different rank for this range:
        # bind it to this job's spec before anyone reads it (ADR-8).
        rendered = stored.value.model_copy(update={"clip_id": spec.clip_id, "spec": spec})
        rendered_ref = f"{job_id}/clips/{clip_id}.rendered.json"
        _write_json(deps, rendered_ref, rendered)
        deps.volume.commit()

        state = _set_clip(
            deps.store.get_clip(job_id, clip_id), status=ClipStatus.DONE, result_ref=rendered_ref
        )
        deps.store.save_clip(job_id, state)
        if not state.telegram_sent:
            _deliver(deps, job, state, rendered)
        _maybe_package(deps, job_id)

    _guarded(deps, Step.CLIP, job_id, body, clip_id=clip_id)


def _deliver(deps: Deps, job: Job, state: ClipState, rendered: RenderedClip) -> None:
    """Send a finished clip, then record that it was sent (a crash in between sends twice)."""
    deps.notifier(job).clip_ready(job, state, rendered)
    deps.store.save_clip(job.job_id, _set_clip(state, telegram_sent=True))


def package_step(deps: Deps, job_id: str) -> None:
    def body(job: Job) -> None:
        clips = deps.store.clips(job_id, job.clip_ids)
        rendered = [
            load_ref(deps.root, c.result_ref, RenderedClip)
            for c in clips
            if c.status is ClipStatus.DONE and c.result_ref is not None
        ]
        if not rendered:
            raise PermanentError(f"all {len(clips)} clips failed")
        source = _output(deps, job, StageName.INGEST, SourceMedia)
        transcript = _output(deps, job, StageName.TRANSCRIBE, Transcript)
        _start(deps, job_id, StageName.PACKAGE)
        stored = deps.stages.package(deps.context(job_id), job, source, transcript, rendered)
        deps.volume.commit()

        job = deps.store.get(job_id)
        job = _set(
            job,
            status=JobStatus.DONE,
            outputs={**job.outputs, StageName.PACKAGE: stored.ref},
            output_zip=stored.value.zip_path,
        )
        # Notify before saving DONE: a crash in between re-runs package (cached) and notifies
        # again, instead of the retry seeing DONE and never sending the zip link.
        deps.notifier(job).done(job)
        # Queue before saving DONE too: a retry that sees DONE returns without queueing.
        _enqueue_posts(deps, job, rendered)
        deps.store.save(job)
        # After the DONE save: the jobs row is a best-effort mirror (`jobs backfill` recreates
        # it), so a slow or down database never delays the DONE status.
        record_job_with_costs(deps, job, stored.value.metadata_path)

    _guarded(deps, Step.PACKAGE, job_id, body)


def _enqueue_posts(deps: Deps, job: Job, rendered: list[RenderedClip]) -> None:
    """Queue a channel job's clips for posting (ADR-23). Never fails the step: a bad queue
    is fixed with `POST /posting/rebuild`, a failed job is not."""
    if job.input.channel is None:
        return
    if deps.posting is None:
        log.info("posting is not configured: %s is not queued", job.job_id)
        return
    try:
        clips = [ClipFacts.from_rendered(r) for r in rendered]
        added = enqueue_job(deps.posting, job, clips, utcnow(), deps.version)
        log.info("queued %d clip(s) of %s for posting", added, job.job_id)
    except Exception as exc:
        log.exception("queueing %s for posting failed", job.job_id)
        if deps.ops is not None:
            deps.ops.alert(f"Queueing {job.job_id} for posting failed: {redact(exc)}. "
                           "Fix it, then POST /posting/rebuild.", "enqueue", job.job_id,
                           path=f"/jobs/{job.job_id}")  # fmt: skip


def dispatch(deps: Deps, step: str, job_id: str, clip_id: str | None = None) -> None:
    """Run one step by name: what a spawned Modal function (or the test harness) calls."""
    match Step(step):
        case Step.INGEST:
            ingest_step(deps, job_id)
        case Step.TRANSCRIBE:
            transcribe_step(deps, job_id)
        case Step.HIGHLIGHTS:
            highlights_step(deps, job_id)
        case Step.CLIP:
            if clip_id is None:
                raise ValueError("the clip step needs a clip_id")
            clip_step(deps, job_id, clip_id)
        case Step.PACKAGE:
            package_step(deps, job_id)


# ---- recovery (ADR-12, ADR-15)


class JobNotResumable(Exception):
    """Resume was asked for a job that is still queued or running."""


def resume(deps: Deps, job_id: str) -> Step | None:
    """Continue a failed job from its first incomplete step; cached work is skipped.

    Returns the step spawned, or None for a job that is already done.
    """
    job = deps.store.get(job_id)
    if job.status is JobStatus.DONE:
        return None
    if job.status is not JobStatus.FAILED:
        raise JobNotResumable(
            f"job {job_id} is still {job.status}; only failed jobs can be resumed"
        )

    deps.store.release(job_id, "failed")
    deps.store.release_all(job_id, "spawn:")
    deps.store.reset_attempts(job_id)
    job = _set(job, status=JobStatus.RUNNING, error=None)
    deps.store.save(job)
    record_job(deps, job)

    for stage, step in (
        (StageName.INGEST, Step.INGEST),
        (StageName.TRANSCRIBE, Step.TRANSCRIBE),
        (StageName.HIGHLIGHTS, Step.HIGHLIGHTS),
    ):
        if stage not in job.outputs:
            deps.spawner.spawn(step, job_id)
            return step

    deps.store.release(job_id, "package")
    unfinished = [
        c for c in deps.store.clips(job_id, job.clip_ids) if c.status is not ClipStatus.DONE
    ]
    if not unfinished:
        deps.store.claim(job_id, "package")  # a late duplicate clip step must not spawn it again
        deps.spawner.spawn(Step.PACKAGE, job_id)
        return Step.PACKAGE
    for clip in unfinished:
        deps.store.save_clip(job_id, _set_clip(clip, status=ClipStatus.PENDING, error=None))
        deps.spawner.spawn(Step.CLIP, job_id, clip.clip_id)
    return Step.CLIP


_STAGE_STEP: dict[StageName | None, Step] = {
    None: Step.INGEST,
    StageName.INGEST: Step.INGEST,
    StageName.TRANSCRIBE: Step.TRANSCRIBE,
    StageName.HIGHLIGHTS: Step.HIGHLIGHTS,
    StageName.REFRAME: Step.CLIP,
    StageName.CAPTIONS: Step.CLIP,
    StageName.RENDER: Step.CLIP,
    StageName.PACKAGE: Step.PACKAGE,
}


def sweep(deps: Deps, now: datetime | None = None) -> list[str]:
    """Fail jobs not updated for longer than their current step's timeout + margin (ADR-15)."""
    now = now or utcnow()
    failed: list[str] = []
    for job_id in deps.store.list_job_ids():
        try:
            job = deps.store.get(job_id)
        except KeyError:
            continue
        if job.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
            continue
        step = _STAGE_STEP[job.stage]
        last = job.updated_at
        if step is Step.CLIP:
            last = max([last, *(c.updated_at for c in deps.store.clips(job_id, job.clip_ids))])
        idle_s = (now - last).total_seconds()
        if idle_s <= STEP_TIMEOUT_S[step] + STALL_MARGIN_S:
            continue
        stage = job.stage or StageName.INGEST
        message = f"stalled at {stage} (no progress for {idle_s / 60:.0f} min)"
        if fail_job(deps, job_id, stage, "stalled", message):
            failed.append(job_id)
    return failed
