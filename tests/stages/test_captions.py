import json
from pathlib import Path

from clipforge.config import Settings
from clipforge.models import Segment, Transcript, Word
from clipforge.prompts import load_prompt
from clipforge.stages import captions
from clipforge.stages.captions import (
    POP,
    TITLE_MAX_WORDS,
    CaptionsDeps,
    TitleCard,
    ass_time,
    build_ass,
    build_srt,
    chunk_words,
    clip_words,
    pick_keywords,
    srt_time,
    title_words,
)
from tests.stages.helpers import FakeLLM, make_ctx
from tests.test_models import make_spec


def w(text: str, start: float, end: float) -> Word:
    return Word(text=text, start=start, end=end)


def transcript_of(words: list[Word]) -> Transcript:
    segment = Segment(start=words[0].start, end=words[-1].end, text="", words=words)
    return Transcript(language="en", duration_s=1800.0, model="fake", segments=[segment])


def dialogues(ass: str) -> list[str]:
    return [line for line in ass.splitlines() if line.startswith("Dialogue:")]


def test_time_formats() -> None:
    assert ass_time(0) == "0:00:00.00" and ass_time(3723.456) == "1:02:03.46"
    assert srt_time(0) == "00:00:00,000" and srt_time(3723.456) == "01:02:03,456"


def test_clip_words_are_shifted_clamped_and_filtered() -> None:
    t = transcript_of(
        [w("before", 8.0, 9.5), w("edge", 9.8, 10.3), w("in", 11.0, 11.2), w("after", 21.0, 22.0)]
    )
    got = clip_words(t, 10.0, 20.0)
    assert [(x.text, x.start, x.end) for x in got] == [("edge", 0.0, 0.3), ("in", 1.0, 1.2)]


def test_chunks_break_on_size_duration_punctuation_and_gaps() -> None:
    words = [
        w("one", 0.0, 0.2),
        w("two", 0.3, 0.5),
        w("three", 0.6, 0.8),
        w("four.", 0.9, 1.1),
        w("five", 1.2, 1.4),
        w("six", 2.5, 2.7),
        w("long", 2.8, 4.6),
    ]
    assert [[x.text for x in c] for c in chunk_words(words)] == [
        ["one", "two", "three"],
        ["four."],
        ["five"],
        ["six"],
        ["long"],
    ]


def test_build_ass_one_event_per_chunk_lower_and_white() -> None:
    chunks = [[w("hello", 0.5, 0.9), w("world", 1.0, 1.4)], [w("again", 1.6, 2.0)]]
    ass = build_ass(chunks)
    assert "PlayResX: 1080" in ass and "PlayResY: 1920" in ass
    assert "Style: Default,Anton," in ass and ",1,7,0,2,60,60,380,1" in ass  # border 7, MarginV 380
    events = dialogues(ass)
    assert len(events) == 2  # no word-by-word karaoke
    # a short gap to the next chunk is bridged so the captions don't flicker
    assert events[0].startswith("Dialogue: 0,0:00:00.50,0:00:01.60,Default")
    assert events[0].endswith(POP + "HELLO WORLD") and "\\c" not in events[0]
    assert events[1].split(",")[1:3] == ["0:00:01.60", "0:00:02.00"]


def test_build_ass_colors_only_the_keywords() -> None:
    chunks = [[w("the", 0.0, 0.2), w("ocean", 0.3, 0.6)], [w("is", 0.7, 0.8), w("big", 0.9, 1.2)]]
    events = dialogues(build_ass(chunks, keywords={1, 3}))
    assert events[0].endswith(POP + "THE {\\c&H0000FFFF&}OCEAN{\\c&H00FFFFFF&}")
    assert events[1].endswith(POP + "IS {\\c&H0000FFFF&}BIG{\\c&H00FFFFFF&}")


def test_ass_control_characters_are_stripped() -> None:
    events = dialogues(build_ass([[w("{\\b1}hack\\N", 0.0, 0.5), w("ok", 0.6, 0.9)]], {0}))
    text = events[0].split(",", 9)[9]
    assert "\\b1" not in text and "\\N" not in text
    assert text.removeprefix(POP).count("{") == 2  # only our two color tags
    assert "HACK" in text


def test_build_srt() -> None:
    srt = build_srt([[w("Hello", 0.5, 0.9), w("there.", 1.0, 1.4)], [w("Bye", 2.0, 2.3)]])
    assert srt.split("\n\n")[0] == "1\n00:00:00,500 --> 00:00:01,400\nHello there."
    assert srt.strip().split("\n\n")[1] == "2\n00:00:02,000 --> 00:00:02,300\nBye"


def test_run_writes_cached_files(tmp_path: Path) -> None:
    spec = make_spec()  # 812.4 → 871.9
    t = transcript_of([w("inside", 812.6, 813.0), w("clip.", 813.1, 813.5)])
    ctx = make_ctx(tmp_path)
    first = captions.run(ctx, spec, t)
    second = captions.run(ctx, spec, t)
    assert first == second
    files = first.value
    assert files.offset_s == spec.start and files.style == "default"
    events = dialogues(ctx.path(files.ass_path).read_text())
    assert len([e for e in events if ",Default," in e]) == 1  # one caption line, 2 words
    assert "inside clip." in ctx.path(files.srt_path).read_text()


# ---- key words chosen by the LLM (prompts/keywords_v1.md)

SETTINGS = Settings(_env_file=None)
_TEXT = "the greatest lesson the ocean gave me is humility and 76 percent"
WORDS = [w(t, i * 0.4, i * 0.4 + 0.3) for i, t in enumerate(_TEXT.split(" "))]


def _deps(*replies: str) -> tuple[CaptionsDeps, FakeLLM]:
    answers = list(replies)
    llm = FakeLLM(respond=lambda _messages: answers.pop(0))
    prompt = load_prompt(captions.KEYWORDS_PROMPT, SETTINGS.prompts_dir)
    return CaptionsDeps(llm=llm, prompt=prompt, settings=SETTINGS), llm


def _keywords(*indices: int, title: int | None = None) -> str:
    return json.dumps({"keywords": list(indices), "title_keyword": title})


def test_pick_keywords_uses_the_llm_choice(tmp_path: Path) -> None:
    deps, llm = _deps(_keywords(2, 4, 10))
    chunks = chunk_words(WORDS)
    assert pick_keywords(make_ctx(tmp_path), deps, WORDS, chunks).words == {2, 4, 10}
    prompt = llm.calls[0][0]["content"]
    assert "2 LESSON" in prompt and "10 76" in prompt  # numbered, uppercase words


def test_pick_keywords_keeps_one_per_chunk_and_caps_density(tmp_path: Path) -> None:
    chunks = chunk_words(WORDS)  # 4 chunks of 3 words
    deps, _ = _deps(_keywords(0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11))
    picked = pick_keywords(make_ctx(tmp_path), deps, WORDS, chunks).words
    assert len(picked) <= max(1, len(WORDS) // 4)
    for chunk_start in range(0, len(WORDS), 3):
        assert len(picked & set(range(chunk_start, chunk_start + 3))) <= 1


def test_pick_keywords_retries_invalid_reply(tmp_path: Path) -> None:
    deps, llm = _deps("sure! here you go", _keywords(99), _keywords(4))
    # first reply: no JSON; retry: index out of range -> after two tries, give up (rule 5)
    assert pick_keywords(make_ctx(tmp_path), deps, WORDS, chunk_words(WORDS)).words == frozenset()
    assert len(llm.calls) == 2
    assert "not valid" in llm.calls[1][-1]["content"]


def test_pick_keywords_second_try_succeeds(tmp_path: Path) -> None:
    deps, llm = _deps("{bad json", _keywords(4))
    assert pick_keywords(make_ctx(tmp_path), deps, WORDS, chunk_words(WORDS)).words == {4}
    assert len(llm.calls) == 2


def test_pick_keywords_records_llm_cost(tmp_path: Path) -> None:
    ctx = make_ctx(tmp_path)
    deps, _ = _deps(_keywords(4))
    pick_keywords(ctx, deps, WORDS, chunk_words(WORDS))
    [cost] = [c for c in ctx.job().cost.stages if c.stage.value == "captions"]
    assert cost.llm_calls == 1 and cost.llm_input_tokens == 1000 and cost.usd_estimate > 0


def test_run_with_keywords_colors_them_and_keys_the_cache(tmp_path: Path) -> None:
    ctx = make_ctx(tmp_path)
    spec = make_spec()
    t = transcript_of([w(x.text, spec.start + x.start, spec.start + x.end) for x in WORDS])
    deps, _ = _deps(_keywords(4))
    with_llm = captions.run(ctx, spec, t, deps)
    plain = captions.run(ctx, spec, t)
    assert with_llm.ref != plain.ref  # prompt + model are part of the cache key
    ass = ctx.path(with_llm.value.ass_path).read_text()
    assert "{\\c&H0000FFFF&}OCEAN{\\c&H00FFFFFF&}" in ass
    assert "\\c&H0000FFFF&" not in ctx.path(plain.value.ass_path).read_text()


def test_empty_clip_needs_no_llm_call(tmp_path: Path) -> None:
    deps, llm = _deps()
    assert pick_keywords(make_ctx(tmp_path), deps, [], []).words == frozenset()
    assert llm.calls == []


def _title_event(ass: str) -> str:
    [event] = [line for line in dialogues(ass) if ",Title," in line]
    return event


def test_title_card_first_three_seconds_with_key_word() -> None:
    title = TitleCard(words=("BELONGING", "MEANS", "BEING", "YOU"), key=3, end=3.0)
    ass = build_ass([[w("hello", 0.5, 0.9)]], title=title)
    assert "Style: Title,Anton,86," in ass and ",8,90,90,230,1" in ass  # top-center, MarginV 230
    event = _title_event(ass)
    assert event.startswith("Dialogue: 1,0:00:00.00,0:00:03.00,Title")
    assert event.endswith("{\\fad(0,300)}BELONGING MEANS BEING {\\c&H0000FFFF&}YOU{\\c&H00FFFFFF&}")


def test_title_ends_with_short_clips() -> None:
    title = TitleCard(words=("SHORT",), key=None, end=2.2)
    assert _title_event(build_ass([[w("a", 0.0, 0.5)]], title=title)).split(",")[2] == "0:00:02.20"


def test_title_is_cleaned_truncated_and_optional() -> None:
    assert title_words("  {\\b1}hack\\N the  world ") == ("HACK", "THE", "WORLD")
    assert len(title_words(" ".join(["word"] * 20))) == TITLE_MAX_WORDS
    assert title_words("") == () and title_words("{}") == ()
    assert ",Title," not in "\n".join(dialogues(build_ass([[w("a", 0.0, 0.5)]], title=None)))


def test_title_keeps_accents() -> None:
    assert title_words("el éxito del corazón") == ("EL", "ÉXITO", "DEL", "CORAZÓN")


def test_every_caption_line_pops() -> None:
    events = dialogues(build_ass([[w("a", 0.0, 0.4)], [w("b", 1.5, 2.0)]]))
    assert len(events) == 2 and all(e.split(",", 9)[9].startswith(POP) for e in events)


def test_pick_keywords_returns_the_title_word(tmp_path: Path) -> None:
    deps, llm = _deps(_keywords(4, title=1))
    title = ("GREATEST", "LESSON")
    picked = pick_keywords(make_ctx(tmp_path), deps, WORDS, chunk_words(WORDS), title)
    assert picked.words == {4} and picked.title_word == 1
    assert "T1 LESSON" in llm.calls[0][0]["content"]


def test_v1_style_reply_is_accepted(tmp_path: Path) -> None:
    deps, _ = _deps(json.dumps({"keywords": [4]}))
    picked = pick_keywords(make_ctx(tmp_path), deps, WORDS, chunk_words(WORDS), ("A",))
    assert picked.words == {4} and picked.title_word is None


def test_title_index_out_of_range_is_retried(tmp_path: Path) -> None:
    deps, llm = _deps(_keywords(4, title=7), _keywords(4, title=0))
    picked = pick_keywords(make_ctx(tmp_path), deps, WORDS, chunk_words(WORDS), ("ONE",))
    assert picked.title_word == 0 and len(llm.calls) == 2


def test_run_writes_the_title_from_the_candidate(tmp_path: Path) -> None:
    ctx = make_ctx(tmp_path)
    spec = make_spec()
    spec = spec.model_copy(
        update={"candidate": spec.candidate.model_copy(update={"title": "The ocean lesson"})}
    )
    t = transcript_of([w(x.text, spec.start + x.start, spec.start + x.end) for x in WORDS])
    deps, _ = _deps(_keywords(4, title=1))
    ass = ctx.path(captions.run(ctx, spec, t, deps).value.ass_path).read_text()
    assert _title_event(ass).endswith("THE {\\c&H0000FFFF&}OCEAN{\\c&H00FFFFFF&} LESSON")
