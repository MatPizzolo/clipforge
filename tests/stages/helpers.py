"""Shared helpers for stage tests; later tasks append fakes and media assertions."""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from clipforge.ffmpeg import media_info
from clipforge.jobs import DictJobStore, JobContext, utcnow
from clipforge.llm import LLMReply
from clipforge.models import (
    ClipOptions,
    ClipSpec,
    Job,
    JobInput,
    Permission,
    ProbeInfo,
    SourceMedia,
    Transcript,
)
from clipforge.pipeline.deps import MemoryKV
from tests.test_models import make_candidate

JOB_ID = "20260923-cccccccc-0001"


def make_ctx(root: Path, job_input: JobInput | None = None, job_id: str = JOB_ID) -> JobContext:
    store = DictJobStore(MemoryKV())
    now = utcnow()
    job_input = job_input or JobInput(source_path="uploads/none.mp4", permission=Permission.OWN)
    store.save(Job(job_id=job_id, input=job_input, created_at=now, updated_at=now))
    return JobContext(job_id=job_id, root=root, store=store)


def upload(root: Path, src: Path) -> str:
    """Copy `src` under JOBS_ROOT (as a user upload would be) and return its contract path."""
    dest = root / "uploads" / src.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    return f"uploads/{src.name}"


@dataclass
class FakeTranscriber:
    transcript: Transcript
    model_name: str = "fake-whisper"
    calls: list[str | None] = field(default_factory=list)

    def transcribe(self, audio: Path, language: str | None) -> Transcript:
        assert audio.exists()
        self.calls.append(language)
        return self.transcript


@dataclass
class FakeLLM:
    """Answers each call with `respond(messages)`; thread-safe, records every call."""

    respond: Callable[[list[dict[str, str]]], str]
    model: str = "claude-haiku-4-5"
    calls: list[list[dict[str, str]]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def complete(self, messages: list[dict[str, str]], max_tokens: int = 2048) -> LLMReply:
        with self._lock:
            self.calls.append(list(messages))
        return LLMReply(
            self.respond(messages), input_tokens=1000, output_tokens=100, model=self.model
        )


def clip_json(*clips: tuple[float, float, float]) -> str:
    """An LLM reply with clips given as (start, end, score)."""
    return json.dumps(
        {
            "clips": [
                {"start": s, "end": e, "score": sc, "hook": "h", "title": "t", "reason": "r"}
                for s, e, sc in clips
            ]
        }
    )


def assert_vertical_clip(probe: ProbeInfo, expected_s: float) -> None:
    """The output contract every rendered clip must meet (CLAUDE.md testing rules)."""
    assert (probe.width, probe.height) == (1080, 1920)
    assert (probe.video_codec, probe.pix_fmt) == ("h264", "yuv420p")
    assert (probe.n_video_streams, probe.n_audio_streams, probe.audio_codec) == (1, 1, "aac")
    assert abs(probe.duration_s - expected_s) < 0.1
    assert probe.video_duration_s is not None and probe.audio_duration_s is not None
    assert abs(probe.video_duration_s - probe.audio_duration_s) < 0.05  # A/V sync
    assert probe.size_bytes < 50 * 1024 * 1024


def gray_frame(path: Path, t: float) -> bytes:
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-ss",
        f"{t}",
        "-i",
        str(path),
        "-frames:v",
        "1",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gray",
        "-",
    ]
    return subprocess.run(cmd, capture_output=True, check=True).stdout


def band_diff(a: bytes, b: bytes, rows: tuple[int, int] = (1300, 1560), width: int = 1080) -> float:
    """Mean absolute pixel difference in the caption band of two 1080x1920 gray frames."""
    lo, hi = rows[0] * width, rows[1] * width
    return sum(abs(x - y) for x, y in zip(a[lo:hi], b[lo:hi], strict=True)) / (hi - lo)


def source_from(root: Path, path: Path) -> SourceMedia:
    info = media_info(path)
    return SourceMedia(
        video_path=upload(root, path),
        audio_path="unused.wav",
        source_hash=path.name * 2,
        duration_s=info.duration_s,
        fps=info.fps,
        width=info.width,
        height=info.height,
        rotation=info.rotation,
        video_codec=info.video_codec or "",
        size_bytes=1,
    )


def spec_for(source: SourceMedia, mode: str, start: float = 1.0, end: float = 4.0) -> ClipSpec:
    candidate = make_candidate().model_copy(update={"start": start, "end": end})
    return ClipSpec(
        clip_id="clip_01",
        rank=1,
        source=source,
        start=start,
        end=end,
        candidate=candidate,
        options=ClipOptions(reframe=mode),  # type: ignore[arg-type]
    )
