import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from clipforge.config import Settings
from clipforge.models import ClipOptions, StageName, Transcript
from clipforge.pipeline.errors import PermanentError
from clipforge.prompts import load_prompt
from clipforge.stages import highlights
from clipforge.stages.highlights import parse_clips
from tests.builders import build_long_transcript, sentence_bounds
from tests.conftest import llm_fixture
from tests.stages.helpers import FakeLLM, clip_json, make_ctx

SETTINGS = Settings(_env_file=None)
PROMPT = load_prompt("highlights_v1", SETTINGS.prompts_dir)


def window_start(messages: list[dict[str, str]]) -> float:
    match = re.search(r"\[(\d+\.\d)-\d+\.\d\] S1:", messages[0]["content"])
    assert match is not None
    return float(match.group(1))


def run(tmp_path: Path, transcript: Transcript, llm: FakeLLM, **options: float | str | int):
    deps = highlights.HighlightsDeps(llm=llm, prompt=PROMPT, settings=SETTINGS)
    ctx = make_ctx(tmp_path)
    return ctx, highlights.run(ctx, transcript, ClipOptions(**options), deps)  # type: ignore[arg-type]


def test_parse_clips_handles_prose_fences_and_extra_keys() -> None:
    assert len(parse_clips(llm_fixture("llm_fenced.txt")).clips) == 1
    assert parse_clips(llm_fixture("llm_empty.json")).clips == []
    with pytest.raises(ValueError):
        parse_clips(llm_fixture("llm_malformed.txt"))
    with pytest.raises(ValidationError):
        parse_clips(llm_fixture("llm_invalid_schema.json"))
    with pytest.raises(ValueError, match="no JSON"):
        parse_clips("I could not find anything good.")


def test_selects_snaps_and_ranks(tmp_path: Path, long_transcript: Transcript) -> None:
    b = sentence_bounds(long_transcript)

    def respond(messages: list[dict[str, str]]) -> str:
        ws = window_start(messages)
        if ws == 0.0:
            return clip_json((b[10][0] + 0.4, b[20][1] - 0.3, 0.7))
        if 270 <= ws < 300:
            return clip_json((b[80][0] - 0.5, b[92][1] + 0.2, 0.9))
        return '{"clips": []}'

    llm = FakeLLM(respond)
    ctx, stored = run(tmp_path, long_transcript, llm)
    got = [(c.start, c.end, c.score) for c in stored.value.candidates]
    assert got == [(b[80][0], b[92][1], 0.9), (b[10][0], b[20][1], 0.7)]
    assert stored.value.candidates[1].raw_start == pytest.approx(b[10][0] + 0.4)
    assert stored.value.prompt_version == "highlights_v1" and stored.value.model == llm.model
    assert len(llm.calls) == 3
    prompt = llm.calls[0][0]["content"]
    assert "Target clip length: 30–60 seconds." in prompt  # noqa: RUF001 (the prompt's en dash)
    assert "Language: en" in prompt
    llm_costs = [
        c for c in ctx.job().cost.stages if c.stage is StageName.HIGHLIGHTS and c.llm_calls
    ]
    assert len(llm_costs) == 3 and all(c.usd_estimate > 0 for c in llm_costs)


def test_overlapping_windows_are_deduped(tmp_path: Path, long_transcript: Transcript) -> None:
    b = sentence_bounds(long_transcript)
    same = (b[70][0], b[80][1])

    def respond(messages: list[dict[str, str]]) -> str:
        ws = window_start(messages)
        if ws < 270:
            return clip_json((*same, 0.6))
        if ws < 540:
            return clip_json((*same, 0.8))
        return '{"clips": []}'

    _, stored = run(tmp_path, long_transcript, FakeLLM(respond))
    assert [(c.start, c.end, c.score) for c in stored.value.candidates] == [(*same, 0.8)]


def test_invalid_json_is_retried_once_with_the_error(
    tmp_path: Path, long_transcript: Transcript
) -> None:
    b = sentence_bounds(long_transcript)

    def respond(messages: list[dict[str, str]]) -> str:
        if window_start(messages) < 270 and len(messages) == 1:
            return 'Sure! {"clips": [{"start": 1'
        return clip_json((b[10][0], b[20][1], 0.7))

    llm = FakeLLM(respond)
    _, stored = run(tmp_path, long_transcript, llm)
    assert len(llm.calls) == 4
    retry = next(call for call in llm.calls if len(call) == 3)
    assert retry[1]["role"] == "assistant" and "not valid" in retry[2]["content"]
    assert stored.value.candidates


def _first_clip_after(ws: float, b: list[tuple[float, float]]) -> tuple[float, float, float]:
    i = next(k for k, (start, _) in enumerate(b) if start >= ws + 10)
    return (b[i][0], b[i + 11][1], 0.8)


def test_bad_windows_are_dropped_up_to_the_threshold(tmp_path: Path) -> None:
    transcript = build_long_transcript(1200.0)  # 5 windows
    b = sentence_bounds(transcript)

    def respond(messages: list[dict[str, str]]) -> str:
        ws = window_start(messages)
        return "not json" if ws < 270 else clip_json(_first_clip_after(ws, b))

    _, stored = run(tmp_path, transcript, FakeLLM(respond))
    assert len(stored.value.candidates) == 4  # 1 of 5 windows (20%) dropped


def test_too_many_bad_windows_fail_the_stage(tmp_path: Path) -> None:
    transcript = build_long_transcript(1200.0)
    b = sentence_bounds(transcript)

    def respond(messages: list[dict[str, str]]) -> str:
        ws = window_start(messages)
        return "not json" if ws < 540 else clip_json(_first_clip_after(ws, b))

    with pytest.raises(PermanentError, match="2 of 5"):
        run(tmp_path, transcript, FakeLLM(respond))


def test_length_filter(tmp_path: Path, long_transcript: Transcript) -> None:
    b = sentence_bounds(long_transcript)
    reply = clip_json((b[10][0], b[12][1], 0.9), (b[10][0], b[20][1], 0.5))  # ~10.6 s and ~39.8 s
    _, stored = run(tmp_path, long_transcript, FakeLLM(lambda m: reply))
    assert [(c.start, c.end) for c in stored.value.candidates] == [(b[10][0], b[20][1])]


def test_no_candidates_is_permanent(tmp_path: Path, long_transcript: Transcript) -> None:
    with pytest.raises(PermanentError, match="no clip-worthy"):
        run(tmp_path, long_transcript, FakeLLM(lambda m: '{"clips": []}'))


def test_uses_the_requested_language(tmp_path: Path, long_transcript: Transcript) -> None:
    b = sentence_bounds(long_transcript)
    llm = FakeLLM(lambda m: clip_json((b[10][0], b[20][1], 0.7)))
    run(tmp_path, long_transcript, llm, language="pt")
    assert "Language: pt" in llm.calls[0][0]["content"]


def test_results_are_cached(tmp_path: Path, long_transcript: Transcript) -> None:
    b = sentence_bounds(long_transcript)
    llm = FakeLLM(lambda m: clip_json((b[10][0], b[20][1], 0.7)))
    deps = highlights.HighlightsDeps(llm=llm, prompt=PROMPT, settings=SETTINGS)
    ctx = make_ctx(tmp_path)
    first = highlights.run(ctx, long_transcript, ClipOptions(), deps)
    second = highlights.run(ctx, long_transcript, ClipOptions(n=2), deps)  # n is not in the key
    assert first == second and len(llm.calls) == 3


def test_api_errors_propagate_for_the_step_to_retry(
    tmp_path: Path, long_transcript: Transcript
) -> None:
    def respond(messages: list[dict[str, str]]) -> str:
        raise RuntimeError("overloaded")

    with pytest.raises(RuntimeError, match="overloaded"):
        run(tmp_path, long_transcript, FakeLLM(respond))


def test_empty_transcript_is_permanent(tmp_path: Path) -> None:
    empty = Transcript(language="en", duration_s=10.0, model="fake", segments=[])
    with pytest.raises(PermanentError, match="empty"):
        run(tmp_path, empty, FakeLLM(lambda m: '{"clips": []}'))
