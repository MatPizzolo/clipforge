"""Deterministic test data builders (no randomness, so expected values can be computed)."""

from __future__ import annotations

from clipforge.models import Segment, Transcript, Word

VOCAB = [
    "the",
    "ocean",
    "teaches",
    "you",
    "patience",
    "and",
    "respect",
    "every",
    "wave",
    "is",
    "different",
    "so",
    "you",
    "learn",
    "to",
    "listen",
    "before",
    "you",
    "move",
]
WORDS_PER_SENTENCE = 8
WORD_S = 0.3  # word duration
GAP_S = 0.1  # gap between words inside a sentence
PAUSE_S = 0.5  # pause after a sentence (>= 300 ms silence)
LONG_PAUSE_S = 1.2  # after every 10th sentence
WORDS_PER_SEGMENT = 12  # whisper-like segments that don't align with sentences


def build_long_transcript(duration_s: float = 720.0) -> Transcript:
    """~12 min transcript with known sentence ends and silences.

    Sentence i ends with "." (or "?" when i % 5 == 4). Segments are 12 words long, so they
    cut across sentences the way real whisper segments do.
    """
    words: list[Word] = []
    t = 0.0
    i = 0
    sentence_s = WORDS_PER_SENTENCE * WORD_S + (WORDS_PER_SENTENCE - 1) * GAP_S
    while t + sentence_s <= duration_s:
        for j in range(WORDS_PER_SENTENCE):
            text = VOCAB[(i * 7 + j) % len(VOCAB)]
            if j == 0:
                text = text.capitalize()
            if j == WORDS_PER_SENTENCE - 1:
                text += "?" if i % 5 == 4 else "."
            words.append(Word(text=text, start=round(t, 3), end=round(t + WORD_S, 3)))
            t += WORD_S + (GAP_S if j < WORDS_PER_SENTENCE - 1 else 0.0)
        t += LONG_PAUSE_S if i % 10 == 9 else PAUSE_S
        i += 1

    segments = [
        Segment(
            start=chunk[0].start,
            end=chunk[-1].end,
            text=" ".join(w.text for w in chunk),
            words=chunk,
        )
        for chunk in (
            words[k : k + WORDS_PER_SEGMENT] for k in range(0, len(words), WORDS_PER_SEGMENT)
        )
    ]
    return Transcript(
        language="en",
        language_probability=0.99,
        duration_s=duration_s,
        model="fixture",
        segments=segments,
    )


def sentence_bounds(transcript: Transcript) -> list[tuple[float, float]]:
    """(start, end) of each sentence in a transcript built by build_long_transcript."""
    bounds: list[tuple[float, float]] = []
    start: float | None = None
    for word in transcript.words:
        if start is None:
            start = word.start
        if word.text.endswith((".", "?", "!")):
            bounds.append((start, word.end))
            start = None
    return bounds
