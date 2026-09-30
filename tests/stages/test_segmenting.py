from clipforge.models import Transcript, Word
from clipforge.stages.segmenting import (
    cut_points,
    format_window,
    make_windows,
    snap,
    split_sentences,
)


def w(text: str, start: float, end: float) -> Word:
    return Word(text=text, start=start, end=end)


def test_split_on_punctuation_and_long_pauses() -> None:
    words = [
        w("Hello", 0.0, 0.4),
        w("there.", 0.5, 0.9),
        w("Next", 1.0, 1.3),
        w("part", 1.4, 1.7),
        w("after", 3.0, 3.3),
        w("pause", 3.4, 3.7),
        w("«Quoted!»", 3.8, 4.2),
        w("end", 4.3, 4.5),
    ]
    assert [s.text for s in split_sentences(words)] == [
        "Hello there.",
        "Next part",
        "after pause «Quoted!»",
        "end",
    ]


def test_runaway_sentences_are_capped() -> None:
    words = [w("word", i * 0.4, i * 0.4 + 0.3) for i in range(100)]
    assert [len(s.text.split()) for s in split_sentences(words)] == [40, 40, 20]


def test_windows_overlap_and_cover_everything(long_transcript: Transcript) -> None:
    sentences = split_sentences(long_transcript.words)
    windows = make_windows(sentences)
    assert [(win.start, win.end) for win in windows] == [(0, 300), (270, 570), (540, 840)]
    covered = {s for win in windows for s in win.sentences}
    assert covered == set(sentences)
    in_overlap = [s for s in sentences if 270 <= s.start < 300]
    assert in_overlap and all(
        s in windows[0].sentences and s in windows[1].sentences for s in in_overlap
    )


def test_short_transcripts_get_one_window() -> None:
    sentences = split_sentences([w("Hi.", 0.0, 0.5)])
    assert len(make_windows(sentences)) == 1
    assert make_windows([]) == []


def test_format_window_lines(long_transcript: Transcript) -> None:
    window = make_windows(split_sentences(long_transcript.words))[0]
    first = format_window(window).splitlines()[0]
    assert first == "[0.0-3.1] S1: The ocean teaches you patience and respect every."


def test_cut_points_include_silences() -> None:
    words = [w("a", 0.0, 0.2), w("b", 0.3, 0.5), w("c", 1.0, 1.2), w("d.", 1.3, 1.5)]
    points = cut_points(words, split_sentences(words))
    assert 1.0 in points.starts and 0.5 in points.ends  # the 0.5 s gap between b and c
    assert 0.3 not in points.starts  # a 0.1 s gap is not a silence


def test_snap_prefers_boundaries_then_words_then_gives_up() -> None:
    preferred, fallback = [10.0, 20.0], [10.0, 12.4, 20.0]
    assert snap(11.0, preferred, fallback) == 10.0
    assert snap(14.0, preferred, fallback) == 12.4  # no boundary within 3 s, nearest word
    assert snap(50.0, preferred, fallback) is None
