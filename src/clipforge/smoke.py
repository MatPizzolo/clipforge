"""The Modal smoke test (spec §6): one real job on the 10 s fixture, checked end to end.

`app.py::smoke` uploads the fixture, runs the job on Modal and calls `check_smoke`. The checks
live here, Modal-free, so they are unit-tested.
"""

from __future__ import annotations

from clipforge.models import (
    ClipOptions,
    JobInput,
    JobMetadata,
    JobStatus,
    JobView,
    Permission,
    StageName,
)

FIXTURE = "tests/fixtures/talking_head_10s.mp4"
MIN_LEN, MAX_LEN = 5.0, 12.0  # the fixture is one ~10 s passage
TOLERANCE_S = 0.1
TELEGRAM_LIMIT_BYTES = 50_000_000


def smoke_input(source_path: str) -> JobInput:
    return JobInput(
        source_path=source_path,
        permission=Permission.OWN,
        source_label="smoke",
        options=ClipOptions(n=1, min_len=MIN_LEN, max_len=MAX_LEN),
    )


def check_smoke(view: JobView, meta: JobMetadata | None) -> list[str]:
    """Problems with a finished smoke job; an empty list means it passed."""
    if view.status is not JobStatus.DONE:
        if view.error is not None:
            return [f"job {view.status} at {view.error.stage}: {view.error.message}"]
        return [f"job ended {view.status} at {view.stage}"]
    if meta is None:
        return ["metadata.json is missing"]
    problems: list[str] = []
    if len(meta.clips) != 1:
        problems.append(f"expected 1 clip, got {len(meta.clips)}")
    for clip in meta.clips:
        probe = clip.probe
        if (probe.width, probe.height) != (1080, 1920):
            problems.append(f"{clip.clip_id}: {probe.width}x{probe.height}, expected 1080x1920")
        if not MIN_LEN - TOLERANCE_S <= probe.duration_s <= MAX_LEN + TOLERANCE_S:
            wanted = f"{MIN_LEN:g}-{MAX_LEN:g} s"
            problems.append(f"{clip.clip_id}: duration {probe.duration_s:.2f} s outside {wanted}")
        if (probe.n_video_streams, probe.n_audio_streams) != (1, 1):
            streams = f"{probe.n_video_streams}v/{probe.n_audio_streams}a"
            problems.append(f"{clip.clip_id}: streams {streams}, expected 1v/1a")
        if probe.size_bytes >= TELEGRAM_LIMIT_BYTES:
            problems.append(f"{clip.clip_id}: {probe.size_bytes} bytes, over Telegram's 50 MB")
    transcribes = [s for s in meta.cost.stages if s.stage is StageName.TRANSCRIBE]
    if not any(s.gpu_s > 0 or s.cached for s in transcribes):
        problems.append("no GPU seconds recorded (transcribe cost missing)")
    return problems
