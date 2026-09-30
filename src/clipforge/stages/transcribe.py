"""Transcribe: faster-whisper word timestamps (ADR-11). Runs inside transcribe_step on the L4.

`WhisperTranscriber` imports faster-whisper lazily: it is installed only in the GPU image.
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Protocol

from clipforge.config import Settings
from clipforge.hashing import cache_key
from clipforge.jobs import JobContext, Stored, cached_stage
from clipforge.models import Segment, SourceMedia, StageCost, StageName, Transcript, Word
from clipforge.pipeline.errors import PermanentError

STAGE_VERSION = "1"


class Transcriber(Protocol):
    model_name: str

    def transcribe(self, audio: Path, language: str | None) -> Transcript: ...


def to_transcript(
    segments: Iterable[Any],
    language: str,
    language_probability: float | None,
    duration_s: float,
    model_name: str,
) -> Transcript:
    """Convert faster-whisper segments, dropping empty words and clamping bad times."""
    out: list[Segment] = []
    for segment in segments:
        words: list[Word] = []
        for w in segment.words or []:
            text = str(w.word).strip()
            if not text:
                continue
            start = max(0.0, float(w.start))
            end = max(start, float(w.end))
            probability = float(w.probability) if w.probability is not None else None
            words.append(
                Word(text=text, start=round(start, 3), end=round(end, 3), probability=probability)
            )
        if words:
            out.append(
                Segment(
                    start=min(w.start for w in words),
                    end=max(w.end for w in words),
                    text=str(segment.text).strip(),
                    words=words,
                )
            )
    return Transcript(
        language=language,
        language_probability=language_probability,
        duration_s=duration_s,
        model=model_name,
        segments=out,
    )


class WhisperTranscriber:
    """faster-whisper on CUDA, fp16, batched, with word timestamps."""

    def __init__(self, model_path: str, model_name: str, batch_size: int = 16) -> None:
        self.model_path = model_path
        self.model_name = model_name
        self.batch_size = batch_size
        self._pipeline: Any = None

    def _load(self) -> Any:
        if self._pipeline is None:
            from faster_whisper import BatchedInferencePipeline, WhisperModel

            model = WhisperModel(self.model_path, device="cuda", compute_type="float16")
            self._pipeline = BatchedInferencePipeline(model)
        return self._pipeline

    def transcribe(self, audio: Path, language: str | None) -> Transcript:
        segments, info = self._load().transcribe(
            str(audio), batch_size=self.batch_size, word_timestamps=True, language=language
        )
        return to_transcript(
            segments, info.language, info.language_probability, info.duration, self.model_name
        )


def run(
    ctx: JobContext,
    source: SourceMedia,
    transcriber: Transcriber,
    settings: Settings,
    language: str | None,
) -> Stored[Transcript]:
    key = cache_key(
        "transcribe",
        STAGE_VERSION,
        [],
        {
            "source_hash": source.source_hash,
            "language": language or "auto",
            "model": transcriber.model_name,
        },
    )

    def compute(out_dir: Path) -> Transcript:
        ctx.report(StageName.TRANSCRIBE, 5, "transcribing")
        started = time.monotonic()
        transcript = transcriber.transcribe(ctx.path(source.audio_path), language)
        gpu_s = time.monotonic() - started
        ctx.record_cost(
            StageCost(
                stage=StageName.TRANSCRIBE,
                wall_s=gpu_s,
                gpu_s=gpu_s,
                gpu_type=settings.gpu_type,
                usd_estimate=settings.prices.gpu_usd(settings.gpu_type, gpu_s),
            )
        )
        if not transcript.words:
            raise PermanentError("no speech was found in the video")
        return transcript

    return cached_stage(ctx, StageName.TRANSCRIBE, key, Transcript, compute)
