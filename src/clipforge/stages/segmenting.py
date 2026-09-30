"""Transcript text for highlight selection: sentences, overlapping LLM windows, and the
points a clip may be cut at (ARCHITECTURE "Highlight selection")."""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from itertools import pairwise

from clipforge.models import Word

SENTENCE_END = (".", "?", "!", "…", "。", "？", "！")  # noqa: RUF001 (CJK punctuation)
TRAILING = "\"'”’)]»"  # noqa: RUF001 (curly quotes)
LONG_PAUSE_S = 1.0  # a pause this long ends a sentence even without punctuation
MAX_SENTENCE_WORDS = 40
SILENCE_S = 0.3  # a gap this long is a good place to cut


def ends_sentence(text: str) -> bool:
    return text.rstrip(TRAILING).endswith(SENTENCE_END)


@dataclass(frozen=True)
class Sentence:
    start: float
    end: float
    text: str


def split_sentences(words: list[Word]) -> list[Sentence]:
    sentences: list[Sentence] = []
    current: list[Word] = []
    for i, word in enumerate(words):
        current.append(word)
        nxt = words[i + 1] if i + 1 < len(words) else None
        pause = nxt is not None and nxt.start - word.end >= LONG_PAUSE_S
        if nxt is None or pause or ends_sentence(word.text) or len(current) >= MAX_SENTENCE_WORDS:
            text = " ".join(w.text for w in current)
            sentences.append(Sentence(current[0].start, current[-1].end, text))
            current = []
    return sentences


@dataclass(frozen=True)
class Window:
    index: int
    start: float
    end: float
    sentences: tuple[Sentence, ...]


def make_windows(
    sentences: list[Sentence], window_s: float = 300.0, overlap_s: float = 30.0
) -> list[Window]:
    """Windows of `window_s` starting every `window_s - overlap_s`; a sentence belongs to
    every window its start falls in."""
    if not sentences:
        return []
    windows: list[Window] = []
    start = 0.0
    last_start = sentences[-1].start
    while True:
        end = start + window_s
        chunk = tuple(s for s in sentences if start <= s.start < end)
        if chunk:
            windows.append(Window(len(windows), start, end, chunk))
        if end > last_start:
            return windows
        start += window_s - overlap_s


def format_window(window: Window, speaker: str = "S1") -> str:
    """`[start-end] SPEAKER: text`, one sentence per line (the prompt's transcript format)."""
    return "\n".join(f"[{s.start:.1f}-{s.end:.1f}] {speaker}: {s.text}" for s in window.sentences)


@dataclass(frozen=True)
class CutPoints:
    starts: list[float]  # preferred clip starts: sentence starts and speech after a silence
    ends: list[float]  # preferred clip ends: sentence ends and speech before a silence
    word_starts: list[float]  # fallback: any word boundary
    word_ends: list[float]


def cut_points(words: list[Word], sentences: list[Sentence]) -> CutPoints:
    starts = {s.start for s in sentences}
    ends = {s.end for s in sentences}
    for a, b in pairwise(words):
        if b.start - a.end >= SILENCE_S:
            ends.add(a.end)
            starts.add(b.start)
    return CutPoints(
        starts=sorted(starts),
        ends=sorted(ends),
        word_starts=sorted(w.start for w in words),
        word_ends=sorted(w.end for w in words),
    )


def _nearest(t: float, points: list[float]) -> float | None:
    if not points:
        return None
    i = bisect.bisect_left(points, t)
    options = points[max(0, i - 1) : i + 1]
    return min(options, key=lambda p: abs(p - t))


def snap(
    t: float, preferred: list[float], fallback: list[float], tolerance: float = 3.0
) -> float | None:
    for points in (preferred, fallback):
        best = _nearest(t, points)
        if best is not None and abs(best - t) <= tolerance:
            return best
    return None
