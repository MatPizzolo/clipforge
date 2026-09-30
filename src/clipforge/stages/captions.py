"""Captions: ASS (one style preset) and SRT for a clip.

Up to 3 words per line, white uppercase Anton with a 7 px black border. Key words chosen by
the LLM (prompts/keywords_v1.md, ADR-18) are yellow. Positioned bottom-center with MarginV 380
on a 1920 canvas, just above the platform UI in the bottom 20%."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from clipforge.config import Settings
from clipforge.hashing import cache_key
from clipforge.jobs import JobContext, Stored, cached_stage
from clipforge.llm import LLMClient
from clipforge.models import (
    CaptionFiles,
    ClipSpec,
    KeywordsReply,
    StageCost,
    StageName,
    Transcript,
    Word,
)
from clipforge.prompts import Prompt
from clipforge.stages.segmenting import ends_sentence

log = logging.getLogger(__name__)

STAGE_VERSION = "3"  # 3: hook title card + caption pop (ADR-20)
KEYWORDS_PROMPT = "keywords_v2"
KEYWORDS_MAX_TOKENS = 300
WORDS_PER_KEYWORD = 4  # at most one key word per 4 words, and one per caption line
STYLE = "default"
FONT = "Anton"
FONT_SIZE = 110
MARGIN_V = 380
MAX_WORDS = 3
MAX_CHUNK_S = 1.5
CHUNK_GAP_S = 0.5
MIN_EVENT_S = 0.05
WHITE = "&H00FFFFFF&"
KEYWORD = "&H0000FFFF&"  # yellow; ASS colors are &HAABBGGRR
_ASS_OVERRIDE = re.compile(r"\{[^}]*\}")
_ASS_CONTROL = re.compile(r"\\[Nnh]|[{}\\\r\n]")

_HEADER = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{FONT},{FONT_SIZE},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,7,0,2,60,60,{MARGIN_V},1
Style: Title,{FONT},86,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,7,0,8,90,90,230,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""  # noqa: E501


def clip_words(transcript: Transcript, start: float, end: float) -> list[Word]:
    """Words overlapping [start, end), with times relative to `start` and clamped to the clip."""
    duration = end - start
    out: list[Word] = []
    for word in transcript.words:
        if word.end <= start or word.start >= end:
            continue
        s = max(0.0, word.start - start)
        e = min(duration, word.end - start)
        out.append(Word(text=word.text, start=round(s, 3), end=round(max(s, e), 3)))
    return out


def chunk_words(words: list[Word]) -> list[list[Word]]:
    chunks: list[list[Word]] = []
    current: list[Word] = []
    for word in words:
        if current and (
            len(current) >= MAX_WORDS
            or word.end - current[0].start > MAX_CHUNK_S
            or ends_sentence(current[-1].text)
            or word.start - current[-1].end >= CHUNK_GAP_S
        ):
            chunks.append(current)
            current = []
        current.append(word)
    if current:
        chunks.append(current)
    return chunks


def ass_time(t: float) -> str:
    cs = round(t * 100)
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6_000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def srt_time(t: float) -> str:
    ms = round(t * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _clean(text: str) -> str:
    """Remove ASS override/control sequences so speech can't inject styling."""
    return _ASS_CONTROL.sub("", text).strip()


TITLE_S = 3.0
TITLE_FADE_MS = 300
TITLE_MAX_WORDS = 10
POP = "{\\fscx110\\fscy110\\t(0,100,\\fscx100\\fscy100)}"


@dataclass(frozen=True)
class Emphasis:
    words: frozenset[int] = frozenset()  # indices into the clip's words
    title_word: int | None = None  # index into the title's words


@dataclass(frozen=True)
class TitleCard:
    words: tuple[str, ...]
    key: int | None
    end: float  # seconds from the clip start


def title_words(title: str) -> tuple[str, ...]:
    """The hook title's words: cleaned of ASS control characters, uppercase, at most 10."""
    without_tags = _ASS_OVERRIDE.sub("", title)  # drop whole `{...}` blocks, not just braces
    words = (_clean(x).upper() for x in without_tags.split())
    return tuple(w for w in words if w)[:TITLE_MAX_WORDS]


def build_ass(
    chunks: list[list[Word]],
    keywords: frozenset[int] | set[int] = frozenset(),
    title: TitleCard | None = None,
) -> str:
    """One event per caption line (each pops in), plus the hook title card when given.
    `keywords` are indices into the clip's words (all chunks)."""
    lines = [_HEADER]
    if title is not None and title.words:
        shown = [
            f"{{\\c{KEYWORD}}}{word}{{\\c{WHITE}}}" if i == title.key else word
            for i, word in enumerate(title.words)
        ]
        lines.append(
            f"Dialogue: 1,{ass_time(0.0)},{ass_time(title.end)},Title,,0,0,0,,"
            f"{{\\fad(0,{TITLE_FADE_MS})}}" + " ".join(shown)
        )
    index = 0
    for n, chunk in enumerate(chunks):
        tokens = []
        for word in chunk:
            token = _clean(word.text).upper()
            tokens.append(f"{{\\c{KEYWORD}}}{token}{{\\c{WHITE}}}" if index in keywords else token)
            index += 1
        end = chunk[-1].end
        if n + 1 < len(chunks) and chunks[n + 1][0].start - end < CHUNK_GAP_S:
            end = chunks[n + 1][0].start  # bridge short pauses so captions don't flicker
        end = max(end, chunk[0].start + MIN_EVENT_S)
        lines.append(
            f"Dialogue: 0,{ass_time(chunk[0].start)},{ass_time(end)},Default,,0,0,0,,"
            + POP
            + " ".join(tokens)
        )
    return "\n".join(lines) + "\n"


def build_srt(chunks: list[list[Word]]) -> str:
    cues = []
    for n, chunk in enumerate(chunks, start=1):
        text = " ".join(word.text for word in chunk)
        cues.append(f"{n}\n{srt_time(chunk[0].start)} --> {srt_time(chunk[-1].end)}\n{text}")
    return "\n\n".join(cues) + "\n"


@dataclass
class CaptionsDeps:
    llm: LLMClient
    prompt: Prompt  # prompts/keywords_v1.md
    settings: Settings


def _parse_keywords(text: str, n_words: int, n_title: int) -> tuple[list[int], int | None]:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object in the reply")
    reply = KeywordsReply.model_validate_json(text[start : end + 1])
    bad = [i for i in reply.keywords if not 0 <= i < n_words]
    if bad:
        raise ValueError(f"indices out of range 0-{n_words - 1}: {bad[:10]}")
    title = reply.title_keyword
    if title is not None and not 0 <= title < n_title:
        raise ValueError(f"title_keyword {title} out of range 0-{n_title - 1}")
    return reply.keywords, title


def _limit(picked: list[int], chunks: list[list[Word]], n_words: int) -> set[int]:
    """Keep the LLM's order of importance, at most one per line and one per 4 words."""
    line_of: dict[int, int] = {}
    index = 0
    for n, chunk in enumerate(chunks):
        for _ in chunk:
            line_of[index] = n
            index += 1
    cap = max(1, n_words // WORDS_PER_KEYWORD)
    kept: set[int] = set()
    used_lines: set[int] = set()
    for i in picked:
        if len(kept) >= cap:
            break
        if i in kept or line_of[i] in used_lines:
            continue
        kept.add(i)
        used_lines.add(line_of[i])
    return kept


def pick_keywords(
    ctx: JobContext,
    deps: CaptionsDeps,
    words: list[Word],
    chunks: list[list[Word]],
    title: tuple[str, ...] = (),
) -> Emphasis:
    """The words to color, in the captions and the title. An invalid reply is retried once
    with the error (rule 5); after that the clip keeps plain white text rather than failing."""
    if not words:
        return Emphasis()
    listing = "\n".join(f"{i} {_clean(word.text).upper()}" for i, word in enumerate(words))
    cap = max(1, len(words) // WORDS_PER_KEYWORD)
    text = deps.prompt.render(
        language=ctx.job().input.options.language or "auto",
        words=listing,
        max_keywords=str(cap),
        title="\n".join(f"T{i} {word}" for i, word in enumerate(title)) or "(no title)",
    )
    messages = [{"role": "user", "content": text}]
    error = "no reply"
    for _ in range(2):
        reply = deps.llm.complete(messages, max_tokens=KEYWORDS_MAX_TOKENS)
        ctx.record_cost(
            StageCost(
                stage=StageName.CAPTIONS,
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
            picked, title_word = _parse_keywords(reply.text, len(words), len(title))
            return Emphasis(frozenset(_limit(picked, chunks, len(words))), title_word)
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
    log.warning("keywords dropped for %s: %s", ctx.clip_id or ctx.job_id, error[:200])
    return Emphasis()


def run(
    ctx: JobContext, spec: ClipSpec, transcript: Transcript, deps: CaptionsDeps | None = None
) -> Stored[CaptionFiles]:
    """`deps` None means plain white captions (no LLM), e.g. in render tests."""
    words = clip_words(transcript, spec.start, spec.end)
    words_hash = hashlib.sha256(
        json.dumps([w.model_dump(mode="json") for w in words], sort_keys=True).encode()
    ).hexdigest()
    keywords_by = f"{deps.prompt.version}:{deps.llm.model}" if deps is not None else "none"
    key = cache_key(
        "captions",
        STAGE_VERSION,
        [],
        {
            "source_hash": spec.source.source_hash,
            "start": f"{spec.start:.3f}",
            "end": f"{spec.end:.3f}",
            "style": STYLE,
            "words": words_hash,
            "keywords": keywords_by,
            "title": spec.candidate.title,
        },
    )

    def compute(out_dir: Path) -> CaptionFiles:
        chunks = chunk_words(words)
        heading = title_words(spec.candidate.title)
        emphasis = (
            pick_keywords(ctx, deps, words, chunks, heading) if deps is not None else Emphasis()
        )
        card = (
            TitleCard(heading, emphasis.title_word, min(TITLE_S, spec.duration_s))
            if heading
            else None
        )
        ass, srt = out_dir / "clip.ass", out_dir / "clip.srt"
        ass.write_text(build_ass(chunks, emphasis.words, card))
        srt.write_text(build_srt(chunks))
        return CaptionFiles(
            clip_id=spec.clip_id,
            ass_path=ctx.rel(ass),
            srt_path=ctx.rel(srt),
            style=STYLE,
            offset_s=spec.start,
        )

    return cached_stage(ctx, StageName.CAPTIONS, key, CaptionFiles, compute, clip_id=spec.clip_id)
