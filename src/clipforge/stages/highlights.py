"""Highlights: ask the LLM for clip candidates per transcript window, validate the JSON
(retry once with the error), snap to cut points, filter by length, dedupe and rank
(ARCHITECTURE "Highlight selection"; CLAUDE.md rule 5, applied per window)."""

from __future__ import annotations

import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from clipforge.config import Settings
from clipforge.hashing import cache_key, canonical_json
from clipforge.jobs import JobContext, Stored, cached_stage
from clipforge.llm import LLMClient
from clipforge.models import (
    ClipCandidate,
    ClipOptions,
    HighlightsResult,
    LLMClip,
    LLMClipsResponse,
    StageCost,
    StageName,
    Transcript,
)
from clipforge.pipeline.errors import PermanentError
from clipforge.prompts import Prompt
from clipforge.stages.segmenting import (
    CutPoints,
    Window,
    cut_points,
    format_window,
    make_windows,
    snap,
    split_sentences,
)

log = logging.getLogger(__name__)

STAGE_VERSION = "1"
PROMPT_VERSION = "highlights_v1"
MAX_WINDOW_FAILURE_RATE = 0.25
IOU_DUPLICATE = 0.5
MAX_TOKENS = 2048


@dataclass
class HighlightsDeps:
    llm: LLMClient
    prompt: Prompt
    settings: Settings


@dataclass
class _WindowResult:
    index: int
    clips: list[LLMClip]
    error: str | None


def parse_clips(text: str) -> LLMClipsResponse:
    """The JSON object in an LLM reply, tolerating prose and code fences around it."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object in the reply")
    return LLMClipsResponse.model_validate_json(text[start : end + 1])


def run(
    ctx: JobContext, transcript: Transcript, options: ClipOptions, deps: HighlightsDeps
) -> Stored[HighlightsResult]:
    language = options.language or transcript.language
    transcript_hash = hashlib.sha256(canonical_json(transcript).encode()).hexdigest()
    key = cache_key(
        "highlights",
        STAGE_VERSION,
        [],
        {
            "transcript": transcript_hash,
            "min_len": f"{options.min_len:g}",
            "max_len": f"{options.max_len:g}",
            "language": language,
            "prompt": deps.prompt.version,
            "model": deps.llm.model,
        },
    )

    def compute(out_dir: Path) -> HighlightsResult:
        words = transcript.words
        sentences = split_sentences(words)
        windows = make_windows(sentences)
        if not windows:
            raise PermanentError("the transcript is empty")
        workers = max(1, deps.settings.llm_max_workers)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(
                pool.map(lambda w: _ask_window(ctx, deps, w, options, language), windows)
            )
        _write_report(out_dir, windows, results)

        failed = [r for r in results if r.error is not None]
        if len(failed) / len(windows) > MAX_WINDOW_FAILURE_RATE:
            raise PermanentError(
                f"the LLM returned invalid JSON for {len(failed)} of {len(windows)} "
                "transcript windows"
            )
        for r in failed:
            log.warning("highlights window %d dropped: %s", r.index, r.error)

        points = cut_points(words, sentences)
        candidates = [
            c
            for r in results
            for clip in r.clips
            if (c := _snap(clip, r.index, points, options)) is not None
        ]
        ranked = _dedupe(sorted(candidates, key=lambda c: c.score, reverse=True))
        if not ranked:
            raise PermanentError("no clip-worthy segments found in this video")
        ctx.report(StageName.HIGHLIGHTS, 100, f"{len(ranked)} candidates")
        return HighlightsResult(
            candidates=ranked, prompt_version=deps.prompt.version, model=deps.llm.model
        )

    return cached_stage(ctx, StageName.HIGHLIGHTS, key, HighlightsResult, compute)


def _ask_window(
    ctx: JobContext, deps: HighlightsDeps, window: Window, options: ClipOptions, language: str
) -> _WindowResult:
    text = deps.prompt.render(
        min_len=f"{options.min_len:g}",
        max_len=f"{options.max_len:g}",
        language=language,
        transcript=format_window(window),
    )
    messages = [{"role": "user", "content": text}]
    error = "no reply"
    for _ in range(2):  # first try + one retry with the validation error (rule 5)
        reply = deps.llm.complete(messages, max_tokens=MAX_TOKENS)
        ctx.record_cost(
            StageCost(
                stage=StageName.HIGHLIGHTS,
                llm_model=reply.model,
                llm_input_tokens=reply.input_tokens,
                llm_output_tokens=reply.output_tokens,
                llm_calls=1,
                usd_estimate=deps.settings.prices.llm_usd(
                    reply.model, reply.input_tokens, reply.output_tokens
                ),
            )
        )
        try:
            return _WindowResult(window.index, parse_clips(reply.text).clips, None)
        except ValueError as exc:  # json and pydantic validation errors
            error = str(exc)
            messages = [
                *messages,
                {"role": "assistant", "content": reply.text},
                {
                    "role": "user",
                    "content": f"Your reply was not valid: {error[:500]}\n"
                    "Return only the corrected JSON object, with no prose.",
                },
            ]
    return _WindowResult(window.index, [], error)


def _snap(
    clip: LLMClip, window_index: int, points: CutPoints, options: ClipOptions
) -> ClipCandidate | None:
    start = snap(clip.start, points.starts, points.word_starts)
    end = snap(clip.end, points.ends, points.word_ends)
    if start is None or end is None or end <= start:
        return None
    if not options.min_len <= end - start <= options.max_len:
        return None
    return ClipCandidate(
        start=start,
        end=end,
        score=clip.score,
        hook=clip.hook,
        title=clip.title,
        reason=clip.reason,
        window_index=window_index,
        raw_start=clip.start,
        raw_end=clip.end,
    )


def _iou(a: ClipCandidate, b: ClipCandidate) -> float:
    inter = max(0.0, min(a.end, b.end) - max(a.start, b.start))
    union = max(a.end, b.end) - min(a.start, b.start)
    return inter / union if union > 0 else 0.0


def _dedupe(ranked: list[ClipCandidate]) -> list[ClipCandidate]:
    kept: list[ClipCandidate] = []
    for candidate in ranked:
        if all(_iou(candidate, k) <= IOU_DUPLICATE for k in kept):
            kept.append(candidate)
    return kept


def _write_report(out_dir: Path, windows: list[Window], results: list[_WindowResult]) -> None:
    """windows.json next to the cached result, for debugging prompt quality."""
    report = [
        {"index": w.index, "start": w.start, "end": w.end, "clips": len(r.clips), "error": r.error}
        for w, r in zip(windows, results, strict=True)
    ]
    (out_dir / "windows.json").write_text(json.dumps(report, indent=2))
