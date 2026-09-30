"""The real StageRunner: wires the stage modules to their clients (Plan 1's chain calls this).

Plan 3 builds one per Modal container with `PipelineStages.from_settings(...)`."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import httpx

from clipforge.config import Settings
from clipforge.jobs import JobContext, Stored
from clipforge.llm import AnthropicClient, LLMClient
from clipforge.models import (
    ClipOptions,
    ClipSpec,
    HighlightsResult,
    Job,
    JobInput,
    PackageResult,
    RenderedClip,
    SourceMedia,
    StageName,
    Transcript,
)
from clipforge.prompts import Prompt, load_prompt
from clipforge.stages import (
    captions,
    faces,
    highlights,
    ingest,
    package,
    reframe,
    render,
    transcribe,
)

STAGE_VERSIONS: dict[str, str] = {
    "ingest": ingest.STAGE_VERSION,
    "transcribe": transcribe.STAGE_VERSION,
    "highlights": highlights.STAGE_VERSION,
    "reframe": reframe.STAGE_VERSION,
    "captions": captions.STAGE_VERSION,
    "render": render.STAGE_VERSION,
    "package": package.STAGE_VERSION,
}


def producer_version(settings: Settings) -> str:
    """What made a clip, from code facts only: "clips:" + 8 hex of the stage versions,
    prompt names and model ids (draft ADR-43). The git SHA is the `build`, kept apart."""
    facts = {
        "stages": dict(sorted(STAGE_VERSIONS.items())),
        "prompts": sorted([highlights.PROMPT_VERSION, captions.KEYWORDS_PROMPT]),
        "models": sorted([settings.highlight_model, settings.whisper_model]),
    }
    digest = hashlib.sha256(json.dumps(facts, sort_keys=True).encode()).hexdigest()
    return f"clips:{digest[:8]}"


@dataclass
class PipelineStages:
    settings: Settings
    http: httpx.Client
    transcriber: transcribe.Transcriber
    llm: LLMClient
    prompt: Prompt
    keywords_prompt: Prompt
    detector: faces.FaceDetector

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        transcriber: transcribe.Transcriber | None = None,
        llm: LLMClient | None = None,
        detector: faces.FaceDetector | None = None,
    ) -> PipelineStages:
        if llm is None:
            if settings.anthropic_api_key is None:
                raise RuntimeError("ANTHROPIC_API_KEY is not configured")
            llm = AnthropicClient(
                api_key=settings.anthropic_api_key.get_secret_value(),
                model=settings.highlight_model,
            )
        return cls(
            settings=settings,
            http=httpx.Client(),
            transcriber=transcriber
            or transcribe.WhisperTranscriber(settings.whisper_model_path, settings.whisper_model),
            llm=llm,
            prompt=load_prompt(highlights.PROMPT_VERSION, settings.prompts_dir),
            keywords_prompt=load_prompt(captions.KEYWORDS_PROMPT, settings.prompts_dir),
            detector=detector or faces.YuNetDetector(settings.models_dir / faces.YUNET_MODEL),
        )

    def ingest(self, ctx: JobContext, job_input: JobInput) -> Stored[SourceMedia]:
        return ingest.run(ctx, job_input, ingest.IngestDeps(http=self.http, settings=self.settings))

    def transcribe(self, ctx: JobContext, source: SourceMedia) -> Stored[Transcript]:
        language = ctx.job().input.options.language
        return transcribe.run(ctx, source, self.transcriber, self.settings, language)

    def highlights(
        self, ctx: JobContext, transcript: Transcript, options: ClipOptions
    ) -> Stored[HighlightsResult]:
        deps = highlights.HighlightsDeps(llm=self.llm, prompt=self.prompt, settings=self.settings)
        return highlights.run(ctx, transcript, options, deps)

    def clip(self, ctx: JobContext, spec: ClipSpec, transcript: Transcript) -> Stored[RenderedClip]:
        ctx.report(StageName.REFRAME, 0, "framing")
        words = captions.clip_words(transcript, spec.start, spec.end)
        track = reframe.track(ctx, spec, words, self.detector, self.settings)
        ctx.report(StageName.CAPTIONS, 10, "captions")
        deps = captions.CaptionsDeps(
            llm=self.llm, prompt=self.keywords_prompt, settings=self.settings
        )
        caps = captions.run(ctx, spec, transcript, deps)
        ctx.report(StageName.RENDER, 30, "rendering")
        return render.run(ctx, spec, track, caps.value, self.settings)

    def package(
        self,
        ctx: JobContext,
        job: Job,
        source: SourceMedia,
        transcript: Transcript,
        rendered: list[RenderedClip],
    ) -> Stored[PackageResult]:
        return package.run(
            ctx,
            job,
            source,
            transcript,
            rendered,
            self.settings,
            STAGE_VERSIONS,
            producer_version(self.settings),
        )
