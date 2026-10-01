"""Modal app (ADR-9): images, the pipeline step functions, the web endpoint, the sweeper and
posting_tick crons and local entrypoints. The only module that imports modal; each function is
one call into the Modal-free code.

    uv run modal run src/clipforge/app.py::doctor    # local + GPU environment checks
    uv run modal run src/clipforge/app.py::smoke     # one real job on the 10 s fixture (~$0.01)
    uv run modal run src/clipforge/app.py::db_doctor # read-only database check (rollout)
    uv run modal deploy src/clipforge/app.py         # deploy the API, webhook and pipeline
"""

from __future__ import annotations

import functools
import os
import time
import uuid
from pathlib import Path

import modal
from fastapi import FastAPI

from clipforge import runtime
from clipforge.api.main import ApiContext, create_app
from clipforge.config import get_settings
from clipforge.db.engine import Database, database_from_settings, redact
from clipforge.pipeline.steps import MAX_ATTEMPTS, STEP_TIMEOUT_S, Deps, Step, dispatch, sweep

APP_NAME = "clipforge"
# Baked into the GPU image at build time. Keep in sync with Settings.whisper_model.
WHISPER_MODEL = "large-v3-turbo"
MODEL_DIR = "/models"
GPU = "L4"
JOBS_ROOT = "/jobs"


def _repo_root(app_file: Path) -> Path:
    """The repo root locally; `/` in a container, where `modal deploy src/clipforge/app.py`
    mounts this file alone at /root/app.py (`.parents[2]` would raise there)."""
    return app_file.parent.parent.parent


REPO_ROOT = _repo_root(Path(__file__).resolve())  # only meaningful locally (image build)
PROMPTS_MOUNT = "/app/prompts"
FONTS_MOUNT = "/app/assets/fonts"
MODELS_MOUNT = "/app/assets/models"  # YuNet face model (ADR-19)
BLUEPRINTS_MOUNT = "/app/blueprints"  # account blueprints (ADR-35)
CONTAINER_ENV = {
    "JOBS_ROOT": JOBS_ROOT,
    "PROMPTS_DIR": PROMPTS_MOUNT,
    "FONTS_DIR": FONTS_MOUNT,
    "MODELS_DIR": MODELS_MOUNT,
    "BLUEPRINTS_DIR": BLUEPRINTS_MOUNT,
    "GIT_SHA": os.environ.get("GIT_SHA", ""),  # set by the CI deploy; empty means unknown
}

app = modal.App(APP_NAME)


# Runs in the image builder as a shell command, not `run_function`: the builder would import
# this file without the clipforge package mounted.
_DOWNLOAD_WHISPER_MODEL = (
    'python -c "from faster_whisper import download_model; '
    f"download_model('{WHISPER_MODEL}', output_dir='{MODEL_DIR}/{WHISPER_MODEL}')\""
)


def _with_app_files(image: modal.Image) -> modal.Image:
    return (
        image.env(CONTAINER_ENV)
        .add_local_dir(REPO_ROOT / "prompts", PROMPTS_MOUNT)
        .add_local_dir(REPO_ROOT / "assets" / "fonts", FONTS_MOUNT)
        .add_local_dir(REPO_ROOT / "assets" / "models", MODELS_MOUNT)
        .add_local_dir(REPO_ROOT / "blueprints", BLUEPRINTS_MOUNT)
        .add_local_python_source("clipforge")
    )


# CPU steps and the web endpoint: ffmpeg (with libass) + the locked project dependencies.
base_image = _with_app_files(
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("ffmpeg", "fontconfig")
    .uv_sync(str(REPO_ROOT))
)

# Pinned on top of uv.lock in the GPU image (ADR-11). faster-whisper 1.2.1 breaks on PyAV 18+
# (a removed argument), so av is pinned too; 17.0.0 has Linux wheels (decision log #70).
WHISPER_PINS = ("faster-whisper==1.2.1", "ctranslate2==4.8.2", "av==17.0.0")

# CUDA 12 + cuDNN 9, as required by CTranslate2 4.x (ADR-11).
whisper_image = _with_app_files(
    modal.Image.from_registry("nvidia/cuda:12.8.1-cudnn-runtime-ubuntu22.04", add_python="3.12")
    .entrypoint([])
    .uv_sync(str(REPO_ROOT))
    .uv_pip_install(*WHISPER_PINS)
    .run_commands(_DOWNLOAD_WHISPER_MODEL)
)

jobs_volume = modal.Volume.from_name("clipforge-jobs", create_if_missing=True)
job_state = modal.Dict.from_name("clipforge-job-state", create_if_missing=True)
secrets = modal.Secret.from_name("clipforge-secrets")

# A 257 MB zip took 600 s on a ~3 Mbit/s connection and hit the old 10 min limit.
WEB_TIMEOUT_S = 3600
# posting_tick: one upload per account, serial; an account not reached is served by the next tick
# within the 30-min window. Each upload is UPLOAD_TIMEOUT_S = 300 s plus the scan and reload.
POSTING_TICK_TIMEOUT_S = 900

RETRIES = modal.Retries(max_retries=MAX_ATTEMPTS - 1, backoff_coefficient=2.0, initial_delay=5.0)


def _spawner() -> runtime.FunctionSpawner:
    return runtime.FunctionSpawner(
        {
            Step.INGEST: ingest_step,
            Step.TRANSCRIBE: transcribe_step,
            Step.HIGHLIGHTS: highlights_step,
            Step.CLIP: clip_step,
            Step.PACKAGE: package_step,
        }
    )


@functools.cache
def _database() -> Database | None:
    """One engine per container; it connects lazily, so code that never queries never connects.
    None until DATABASE_URL is in the secret (rollout step 4c.2, decision log #107)."""
    return database_from_settings(get_settings())


@functools.cache
def _step_deps() -> Deps:
    """One per container: the real stages (LLM client, prompt, transcriber) are built once."""
    from clipforge.stages.runner import PipelineStages

    settings = get_settings()
    return runtime.build_deps(
        settings,
        kv=runtime.DictKV(job_state),
        volume=runtime.ModalVolume(jobs_volume),
        spawner=_spawner(),
        stages=PipelineStages.from_settings(settings),
        sender=runtime.telegram_sender(settings),
        db=_database(),
    )


@functools.cache
def _service_deps() -> Deps:
    """For the web endpoint and the sweeper: jobs are created, read and resumed, never run."""
    settings = get_settings()
    return runtime.build_deps(
        settings,
        kv=runtime.DictKV(job_state),
        volume=runtime.ModalVolume(jobs_volume),
        spawner=_spawner(),
        stages=runtime.UnavailableStages(),
        sender=runtime.telegram_sender(settings),
        db=_database(),
    )


@app.function(
    image=base_image,
    cpu=2.0,
    memory=4096,
    timeout=STEP_TIMEOUT_S[Step.INGEST],
    retries=RETRIES,
    volumes={JOBS_ROOT: jobs_volume},
    secrets=[secrets],
)
def ingest_step(job_id: str) -> None:
    dispatch(_step_deps(), Step.INGEST, job_id)


@app.function(
    image=whisper_image,
    gpu=GPU,
    timeout=STEP_TIMEOUT_S[Step.TRANSCRIBE],
    retries=RETRIES,
    volumes={JOBS_ROOT: jobs_volume},
    secrets=[secrets],
)
def transcribe_step(job_id: str) -> None:
    dispatch(_step_deps(), Step.TRANSCRIBE, job_id)


@app.function(
    image=base_image,
    cpu=1.0,
    timeout=STEP_TIMEOUT_S[Step.HIGHLIGHTS],
    retries=RETRIES,
    volumes={JOBS_ROOT: jobs_volume},
    secrets=[secrets],
)
def highlights_step(job_id: str) -> None:
    dispatch(_step_deps(), Step.HIGHLIGHTS, job_id)


@app.function(
    image=base_image,
    cpu=4.0,
    memory=4096,
    timeout=STEP_TIMEOUT_S[Step.CLIP],
    retries=RETRIES,
    volumes={JOBS_ROOT: jobs_volume},
    secrets=[secrets],
)
def clip_step(job_id: str, clip_id: str) -> None:
    dispatch(_step_deps(), Step.CLIP, job_id, clip_id)


@app.function(
    image=base_image,
    cpu=1.0,
    timeout=STEP_TIMEOUT_S[Step.PACKAGE],
    retries=RETRIES,
    volumes={JOBS_ROOT: jobs_volume},
    secrets=[secrets],
)
def package_step(job_id: str) -> None:
    dispatch(_step_deps(), Step.PACKAGE, job_id)


@app.function(
    image=base_image,
    cpu=0.25,
    timeout=120,
    schedule=modal.Cron("*/10 * * * *"),
    volumes={JOBS_ROOT: jobs_volume},
    secrets=[secrets],
)
def sweeper() -> None:
    failed = sweep(_service_deps())
    if failed:
        print(f"sweeper: failed {len(failed)} stalled job(s): {', '.join(failed)}")


@app.function(
    image=base_image,
    cpu=0.25,
    timeout=POSTING_TICK_TIMEOUT_S,
    schedule=modal.Cron("*/5 * * * *"),
    volumes={JOBS_ROOT: jobs_volume},
    secrets=[secrets],
)
def posting_tick() -> None:
    """Send the next clip to the owner's phone when a posting slot is due (ADR-23)."""
    from clipforge.bot.context import BotContext
    from clipforge.bot.posting import tick
    from clipforge.jobs import utcnow

    settings = get_settings()
    sender = runtime.telegram_sender(settings)
    if sender is None:
        return
    deps = _service_deps()
    try:
        deps.volume.reload()  # see clips rendered since this container started
        print(f"posting_tick: {tick(BotContext(settings, sender, deps), utcnow())}")
    except Exception as exc:
        if deps.ops is not None:
            deps.ops.alert(f"posting_tick crashed: {redact(exc)}", "tick", "crash")
        raise


@app.function(
    image=base_image,
    cpu=0.5,
    timeout=900,
    schedule=modal.Cron("0 7 * * *"),
    volumes={JOBS_ROOT: jobs_volume},
    secrets=[secrets],
)
def posting_daily() -> None:
    """The daily reconcile (ADR-46, was posting_keepalive): keep the Dict's posting keys alive
    and snapshot them (ADR-24), verify against Postgres, backfill job rows, rewrite the schedule
    copies, rebuild the queue and snapshot the posting tables."""
    from clipforge.jobs import utcnow
    from clipforge.posting.daily import run_daily

    deps = _service_deps()
    try:
        deps.volume.reload()
        lines = run_daily(deps, _database(), get_settings().posting_account_id, utcnow())
        deps.volume.commit()
    except Exception as exc:
        if deps.ops is not None:
            deps.ops.alert(f"posting_daily crashed: {redact(exc)}", "daily", "crash")
        raise
    for line in lines:
        print(f"posting_daily: {line}")


@app.function(
    image=base_image,
    cpu=0.5,
    timeout=WEB_TIMEOUT_S,  # long zip downloads; the webhook itself answers in seconds
    volumes={JOBS_ROOT: jobs_volume},
    secrets=[secrets],
)
@modal.asgi_app()
def web() -> FastAPI:
    settings = get_settings()
    sender = runtime.telegram_sender(settings)
    return create_app(
        ApiContext(settings=settings, deps=_service_deps, sender=lambda: sender, db=_database)
    )


@app.function(image=base_image, cpu=0.25, timeout=60, secrets=[secrets])
def db_doctor() -> dict[str, object]:
    """Read-only database check: connect ms, alembic_version vs the code's head, pooled host,
    and accounts whose `posting:schedule:*` copy is missing or stale (run before rollout step
    4c.7). Never writes and never prints the URL (rollout, runbook §4c)."""
    from clipforge.accounts.service import schedule_drift
    from clipforge.db import doctor
    from clipforge.db.accounts import AccountsRepo

    settings = get_settings()
    url = None if settings.database_url is None else settings.database_url.get_secret_value()
    database = database_from_settings(settings)
    report: dict[str, object] = {}
    try:
        report.update(doctor.check(database, url, require_pooled=True))
        if database is not None and report["ok"]:
            try:
                drift = schedule_drift(AccountsRepo(database), runtime.DictKV(job_state))
                report["schedule_drift"] = drift
                report["ok"] = not drift
            except Exception as exc:
                report["ok"], report["error"] = False, f"schedule check: {redact(exc)}"
    finally:
        if database is not None:
            database.dispose()
    for key, value in report.items():
        print(f"db_doctor: {key}: {value}")
    return report


@app.function(image=whisper_image, gpu=GPU, timeout=600)
def gpu_doctor(audio_wav: bytes) -> dict[str, object]:
    """Checks CUDA, CTranslate2 and a real transcription of `audio_wav` on the GPU."""
    import subprocess
    import tempfile

    import av
    import ctranslate2
    from faster_whisper import BatchedInferencePipeline, WhisperModel

    report: dict[str, object] = {
        "gpu": subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip(),
        "ctranslate2": ctranslate2.__version__,
        "av": av.__version__,
        "cuda_devices": ctranslate2.get_cuda_device_count(),
    }

    started = time.monotonic()
    model = WhisperModel(f"{MODEL_DIR}/{WHISPER_MODEL}", device="cuda", compute_type="float16")
    report["load_s"] = round(time.monotonic() - started, 2)

    with tempfile.NamedTemporaryFile(suffix=".wav") as f:
        f.write(audio_wav)
        f.flush()
        started = time.monotonic()
        segments, info = BatchedInferencePipeline(model).transcribe(
            f.name, batch_size=16, word_timestamps=True
        )
        segments = list(segments)
        report["transcribe_s"] = round(time.monotonic() - started, 2)

    report["language"] = f"{info.language} ({info.language_probability:.2f})"
    report["words"] = sum(len(s.words or []) for s in segments)
    report["text"] = " ".join(s.text.strip() for s in segments)
    return report


@app.local_entrypoint()
def doctor(audio: str = "", skip_gpu: bool = False) -> None:
    from clipforge.doctor import DEFAULT_AUDIO_SOURCE, audio_wav_bytes, format_checks, local_checks

    print("Local:")
    checks = local_checks()
    print(format_checks(checks))
    if skip_gpu:
        return

    source = Path(audio) if audio else DEFAULT_AUDIO_SOURCE
    wav = audio_wav_bytes(source)
    print(f"\nModal ({GPU}, {WHISPER_MODEL}) transcribing {source} ({len(wav) / 1e6:.1f} MB wav):")
    started = time.monotonic()
    report = gpu_doctor.remote(wav)
    for key, value in report.items():
        print(f"  {key}: {value}")
    print(f"  round_trip_s: {time.monotonic() - started:.1f} (includes cold start)")


@app.local_entrypoint()
def smoke(timeout_s: int = 900) -> None:
    """One real job on the 10 s fixture (n=1, len 5-9) on Modal; exits non-zero on failure."""
    from clipforge.cli import wait
    from clipforge.jobs import DictJobStore
    from clipforge.models import JobMetadata
    from clipforge.pipeline.deps import NullVolume
    from clipforge.service import create_job, get_job_view
    from clipforge.smoke import FIXTURE, check_smoke, smoke_input

    fixture = REPO_ROOT / FIXTURE
    rel = f"smoke/{uuid.uuid4().hex[:8]}/{fixture.name}"
    with jobs_volume.batch_upload() as batch:
        batch.put_file(str(fixture), f"/{rel}")

    deps = Deps(
        store=DictJobStore(runtime.DictKV(job_state)),
        volume=NullVolume(),  # the job runs in Modal containers; nothing is read locally
        spawner=_spawner(),
        stages=runtime.UnavailableStages(),
        root=Path(JOBS_ROOT),
    )
    started = time.monotonic()
    job = create_job(deps, smoke_input(rel))
    print(f"smoke job {job.job_id}")
    view = wait(lambda: get_job_view(deps.store, deps.root, job.job_id), timeout_s=timeout_s)

    meta = None
    if view.status.value == "done":
        raw = b"".join(jobs_volume.read_file(f"{job.job_id}/output/metadata.json"))
        meta = JobMetadata.model_validate_json(raw)
    problems = check_smoke(view, meta)
    if problems:
        raise SystemExit("smoke FAILED:\n  " + "\n  ".join(problems))
    assert meta is not None  # check_smoke reports a missing metadata.json
    elapsed = time.monotonic() - started
    print(f"smoke OK · {elapsed:.0f} s · ${view.cost.total_usd:.4f} · {meta.clips[0].title!r}")
