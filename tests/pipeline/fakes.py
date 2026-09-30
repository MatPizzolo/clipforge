"""Fake stages for chain tests: real cached_stage and files, no ffmpeg, LLM or GPU."""

from __future__ import annotations

import threading
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from clipforge.hashing import cache_key
from clipforge.jobs import JobContext, Stored, cached_stage
from clipforge.models import (
    ClipCandidate,
    ClipOptions,
    ClipSpec,
    CostSummary,
    HighlightsResult,
    Job,
    JobInput,
    JobMetadata,
    PackagedClip,
    PackageResult,
    ProbeInfo,
    RenderedClip,
    SourceMedia,
    StageCost,
    StageName,
    Transcript,
    Versions,
)
from clipforge.pipeline.errors import PermanentError
from tests.builders import build_long_transcript

SOURCE_DURATION_S = 600.0


def _probe(duration: float) -> ProbeInfo:
    return ProbeInfo(
        width=1080,
        height=1920,
        duration_s=duration,
        video_duration_s=duration,
        audio_duration_s=duration,
        fps=30.0,
        video_codec="h264",
        pix_fmt="yuv420p",
        audio_codec="aac",
        n_video_streams=1,
        n_audio_streams=1,
        size_bytes=1000,
    )


@dataclass
class FakeStages:
    """Configurable failures, keyed by stage name ("ingest", ...) or clip id ("clip_03")."""

    n_candidates: int = 5
    reverse: bool = False  # reverse the ranking (same time ranges, different clip ids)
    transient: Counter[str] = field(default_factory=Counter)  # failures left per name
    permanent: dict[str, str] = field(default_factory=dict)  # name -> user message
    calls: Counter[str] = field(default_factory=Counter)  # every call
    computes: Counter[str] = field(default_factory=Counter)  # cache misses
    packaged: list[str] = field(default_factory=list)  # clip ids given to the last package
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def _enter(self, name: str) -> None:
        with self._lock:
            self.calls[name] += 1
            if self.transient[name] > 0:
                self.transient[name] -= 1
                raise RuntimeError(f"{name} blip")
        if name in self.permanent:
            raise PermanentError(self.permanent[name])

    def _computed(self, name: str) -> None:
        with self._lock:
            self.computes[name] += 1

    def ingest(self, ctx: JobContext, job_input: JobInput) -> Stored[SourceMedia]:
        self._enter("ingest")
        key = cache_key("ingest", "fake", [], {"source": str(job_input.source_url)})

        def compute(out_dir: Path) -> SourceMedia:
            self._computed("ingest")
            (out_dir / "source.mp4").write_bytes(b"video")
            (out_dir / "audio.wav").write_bytes(b"audio")
            ctx.report(StageName.INGEST, 100, "downloaded")
            return SourceMedia(
                video_path=ctx.rel(out_dir / "source.mp4"),
                audio_path=ctx.rel(out_dir / "audio.wav"),
                source_hash="a" * 64,
                duration_s=SOURCE_DURATION_S,
                fps=30.0,
                width=1920,
                height=1080,
                video_codec="h264",
                size_bytes=5,
            )

        return cached_stage(ctx, StageName.INGEST, key, SourceMedia, compute)

    def transcribe(self, ctx: JobContext, source: SourceMedia) -> Stored[Transcript]:
        self._enter("transcribe")
        key = cache_key("transcribe", "fake", [], {"source_hash": source.source_hash})

        def compute(out_dir: Path) -> Transcript:
            self._computed("transcribe")
            ctx.record_cost(
                StageCost(stage=StageName.TRANSCRIBE, gpu_s=10.0, gpu_type="L4", usd_estimate=0.002)
            )
            return build_long_transcript(SOURCE_DURATION_S)

        return cached_stage(ctx, StageName.TRANSCRIBE, key, Transcript, compute)

    def highlights(
        self, ctx: JobContext, transcript: Transcript, options: ClipOptions
    ) -> Stored[HighlightsResult]:
        self._enter("highlights")
        key = cache_key(
            "highlights",
            "fake",
            [],
            {
                "n_candidates": str(self.n_candidates),
                "reverse": str(self.reverse),
                "min": str(options.min_len),
                "max": str(options.max_len),
            },
        )

        def compute(out_dir: Path) -> HighlightsResult:
            self._computed("highlights")
            ctx.record_cost(
                StageCost(
                    stage=StageName.HIGHLIGHTS,
                    llm_model="fake",
                    llm_input_tokens=1000,
                    llm_output_tokens=100,
                    llm_calls=2,
                    usd_estimate=0.0015,
                )
            )
            order = list(range(self.n_candidates))
            if self.reverse:
                order.reverse()
            candidates = [
                ClipCandidate(
                    start=10.0 + 60 * i,
                    end=45.0 + 60 * i,
                    score=round(0.9 - 0.1 * rank, 2),
                    hook=f"hook {i}",
                    title=f"title {i}",
                    reason="fake",
                    window_index=i,
                    raw_start=10.0 + 60 * i,
                    raw_end=45.0 + 60 * i,
                )
                for rank, i in enumerate(order)
            ]
            return HighlightsResult(candidates=candidates, prompt_version="fake_v1", model="fake")

        return cached_stage(ctx, StageName.HIGHLIGHTS, key, HighlightsResult, compute)

    def clip(self, ctx: JobContext, spec: ClipSpec, transcript: Transcript) -> Stored[RenderedClip]:
        self._enter(spec.clip_id)
        # Keyed on the time range, never on clip_id or rank (ADR-8).
        key = cache_key(
            "clip",
            "fake",
            [],
            {
                "source_hash": spec.source.source_hash,
                "start": str(spec.start),
                "end": str(spec.end),
            },
        )

        def compute(out_dir: Path) -> RenderedClip:
            self._computed("clip")
            ctx.report(StageName.RENDER, 50, "rendering")
            ctx.record_cost(StageCost(stage=StageName.RENDER, wall_s=1.0, usd_estimate=0.001))
            (out_dir / "clip.mp4").write_bytes(b"clip")
            (out_dir / "clip.srt").write_text("1\n")
            return RenderedClip(
                clip_id=spec.clip_id,
                spec=spec,
                video_path=ctx.rel(out_dir / "clip.mp4"),
                srt_path=ctx.rel(out_dir / "clip.srt"),
                encoder="libx264",
                probe=_probe(spec.duration_s),
            )

        return cached_stage(ctx, StageName.RENDER, key, RenderedClip, compute, clip_id=spec.clip_id)

    def package(
        self,
        ctx: JobContext,
        job: Job,
        source: SourceMedia,
        transcript: Transcript,
        rendered: list[RenderedClip],
    ) -> Stored[PackageResult]:
        self._enter("package")
        self.packaged = [r.clip_id for r in rendered]
        key = cache_key(
            "package", "fake", [], {"job": job.job_id, "clips": ",".join(self.packaged)}
        )

        def compute(out_dir: Path) -> PackageResult:
            self._computed("package")
            (out_dir / "job.zip").write_bytes(b"zip")
            output = ctx.job_dir / "output"
            output.mkdir(parents=True, exist_ok=True)
            packaged: list[PackagedClip] = []
            for r in sorted(rendered, key=lambda r: r.spec.rank):
                (output / r.clip_id).mkdir(exist_ok=True)
                (output / r.clip_id / "video.mp4").write_bytes(b"clip")
                packaged.append(
                    PackagedClip(
                        clip_id=r.clip_id, rank=r.spec.rank, dir=r.clip_id,
                        video=f"{r.clip_id}/video.mp4", srt=f"{r.clip_id}/captions.srt",
                        post_md=f"{r.clip_id}/post.md", start=r.spec.start, end=r.spec.end,
                        score=r.spec.candidate.score, title=r.spec.candidate.title,
                        hook=r.spec.candidate.hook, probe=r.probe,
                    )
                )  # fmt: skip
            metadata = JobMetadata(
                job_id=job.job_id, input=job.input, source=source,
                transcript_language=transcript.language, clips=packaged, cost=CostSummary(),
                versions=Versions(git_sha=None, clipforge="test", stages={}, highlight_prompt="p",
                                  highlight_model="m", whisper_model="w"),
                started_at=job.created_at, finished_at=job.updated_at,
            )  # fmt: skip
            (output / "metadata.json").write_text(metadata.model_dump_json())
            return PackageResult(
                output_dir=ctx.rel(output),
                zip_path=ctx.rel(out_dir / "job.zip"),
                metadata_path=ctx.rel(output / "metadata.json"),
                clips=packaged,
            )

        return cached_stage(ctx, StageName.PACKAGE, key, PackageResult, compute)
