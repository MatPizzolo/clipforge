from clipforge.models import ClipCandidate, ClipOptions, HighlightsResult
from clipforge.pipeline.selection import AUTO_MAX_CLIPS, select_clips
from tests.test_models import make_source  # 1800 s source


def candidate(start: float, end: float, score: float) -> ClipCandidate:
    return ClipCandidate(
        start=start,
        end=end,
        score=score,
        hook="h",
        title="t",
        reason="r",
        window_index=0,
        raw_start=start,
        raw_end=end,
    )


def test_select_top_n_in_rank_order() -> None:
    result = HighlightsResult(
        candidates=[candidate(10, 50, 0.9), candidate(100, 140, 0.8), candidate(200, 240, 0.7)],
        prompt_version="p",
        model="m",
    )
    specs = select_clips(result, make_source(), ClipOptions(n=2))
    assert [(s.clip_id, s.rank, s.start) for s in specs] == [
        ("clip_01", 1, 10),
        ("clip_02", 2, 100),
    ]


def test_skips_candidates_past_the_source_end() -> None:
    result = HighlightsResult(
        candidates=[candidate(1790, 1830, 0.95), candidate(10, 50, 0.9)],
        prompt_version="p",
        model="m",
    )
    specs = select_clips(result, make_source(), ClipOptions(n=5))
    assert [(s.clip_id, s.start) for s in specs] == [("clip_01", 10)]


def test_no_candidates() -> None:
    empty = HighlightsResult(candidates=[], prompt_version="p", model="m")
    assert select_clips(empty, make_source(), ClipOptions()) == []


def _result(*scores: float) -> HighlightsResult:
    return HighlightsResult(
        candidates=[candidate(10 + 50 * i, 45 + 50 * i, s) for i, s in enumerate(scores)],
        prompt_version="p",
        model="m",
    )


def test_auto_takes_every_candidate_above_the_threshold() -> None:
    specs = select_clips(_result(0.9, 0.85, 0.8, 0.79, 0.5), make_source(), ClipOptions())
    assert [s.candidate.score for s in specs] == [0.9, 0.85, 0.8]  # default min_score 0.80
    assert [s.clip_id for s in specs] == ["clip_01", "clip_02", "clip_03"]


def test_auto_threshold_is_an_option() -> None:
    options = ClipOptions(min_score=0.86)
    assert len(select_clips(_result(0.9, 0.85, 0.8), make_source(), options)) == 1


def test_auto_is_capped_at_30() -> None:
    specs = select_clips(_result(*[0.9] * 34), make_source(), ClipOptions())
    assert len(specs) == AUTO_MAX_CLIPS == 30


def test_explicit_n_ignores_the_threshold() -> None:
    specs = select_clips(_result(0.6, 0.5, 0.4), make_source(), ClipOptions(n=2))
    assert [s.candidate.score for s in specs] == [0.6, 0.5]


def test_auto_with_nothing_above_the_threshold() -> None:
    assert select_clips(_result(0.7, 0.6), make_source(), ClipOptions()) == []
