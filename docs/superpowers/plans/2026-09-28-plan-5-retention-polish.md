> **Historical (ADR-20, 2026-09-28):** built and deployed; docs/ARCHITECTURE.md and the code are current.

# Plan 5: Retention polish (loudness, hook title, caption pop, lighter files)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every clip gets:
- audio normalized to -14 LUFS;
- the LLM's hook title at the top for the first 3 s, with one yellow key word;
- captions that pop in;
- a bitrate that fits the source resolution.

**Architecture:**
- **Render:** a `loudnorm` audio filter goes into the existing single encode, and `video_bitrate` gains a source-height cap.
- **Captions:** they move to a new prompt version (`keywords_v2`) that also picks the title's key word. `build_ass` writes a `Title` style and event plus scale "pop" tags on each caption line, all in the one `.ass` that render already burns in.

**Tech Stack:** ffmpeg (`loudnorm`, `ebur128`, libass `\t`/`\fad`), pydantic v2, pytest.

**Spec:** `docs/superpowers/specs/2026-09-28-retention-polish-design.md` (ADR-20). Rules: `CLAUDE.md`, ADR-18 (caption key words).

## Global Constraints

- Loudness is `loudnorm=I=-14:TP=-1.5:LRA=11`, single-pass, in the render encode. Verified 2026-09-28: a -33.8 LUFS sine comes out at -14.0, and 3 s of the fixture's speech at -14.1.
- Bitrate cap by source height: ≤ 480 → 3 000 000, ≤ 720 → 5 000 000, otherwise 8 000 000 b/s. The Telegram 45 MB budget and the 500 kb/s floor still apply.
- Title: `spec.candidate.title`, cleaned of ASS control characters, uppercase, **at most 10 words**. Style `Title` is Anton 86, white, black outline 7, alignment 8 (top-center), side margins 90, MarginV 230. It's shown from 0 to `min(3.0, clip duration)` with `{\fad(0,300)}`. The key word is yellow `&H0000FFFF&`.
- Caption pop: every caption event text starts with `{\fscx110\fscy110\t(0,100,\fscx100\fscy100)}`.
- Prompts are files (rule 4). `keywords_v1.md` is untouched, and `keywords_v2.md` is new and registered. LLM output is validated with one retry (rule 5). An invalid reply twice gives no yellow anywhere and never fails a clip.
- `captions.STAGE_VERSION = "3"`, `render.STAGE_VERSION = "3"`.
- Output contract unchanged: 1080x1920, h264/yuv420p, AAC 48 kHz stereo, A/V within 50 ms, under 50 MB.
- **The user does all git.** Checkpoints are file lists.

## Review Focus

1. **A title the LLM wrote badly:** too long, with `{`/`\` characters, or empty. It must be truncated to 10 words and cleaned, and an empty title means no title event. Test: Task 2 `test_title_is_cleaned_truncated_and_optional`.
2. **Non-English titles with accents** (Spanish "ÉXITO", "CORAZÓN"): uppercase keeps the accents, and the key word index still points at the right word. Test: Task 2 `test_title_keeps_accents`.
3. **A clip shorter than 3 s:** the title ends at the clip end, not after it. Test: Task 2 `test_title_ends_with_short_clips`.
4. **A v1-style reply without `title_keyword`, or a title index out of range:** the first is accepted with no title key word; the second is retried and then dropped. Test: Task 2 `test_v1_style_reply_is_accepted` and `test_title_index_out_of_range_is_retried`.
5. **A low-res source rendered at a high bitrate:** 360p sources get at most 3 Mb/s. Test: Task 1 `test_bitrate_is_capped_by_source_height`.

---

### Task 1: Render: loudness normalization and bitrate by source height

**Files:**
- Modify: `src/clipforge/stages/render.py`
- Test: `tests/stages/test_render.py`

**Interfaces:**
- Produces:
  - `video_bitrate(duration_s: float, source_height: int = 1080) -> int`;
  - `LOUDNORM = "loudnorm=I=-14:TP=-1.5:LRA=11"`;
  - `render.STAGE_VERSION = "3"`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/stages/test_render.py`:

```python
import re as _re  # noqa: E402  (moved to the top when formatted)
import subprocess as _subprocess  # noqa: E402


def _integrated_lufs(path: Path) -> float:
    out = _subprocess.run(
        ["ffmpeg", "-nostats", "-hide_banner", "-i", str(path), "-af", "ebur128", "-f", "null",
         "-"], capture_output=True, text=True, check=True,
    ).stderr  # fmt: skip
    return float(_re.findall(r"^\s+I:\s+(-?[0-9.]+) LUFS", out, _re.M)[-1])


def test_audio_is_normalized_to_minus_14_lufs(tmp_path: Path) -> None:
    quiet = tmp_path / "quiet.mp4"
    ffmpeg.run([
        "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=6",
        "-f", "lavfi", "-i", "sine=f=440:d=6:sample_rate=48000,volume=-12dB",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", str(quiet),
    ])  # fmt: skip
    assert _integrated_lufs(quiet) < -30  # the source really is quiet
    out = render_clip(tmp_path, spec_for(source_from(tmp_path, quiet), "center"))
    assert abs(_integrated_lufs(out) - (-14.0)) <= 1.5
    assert_vertical_clip(ffmpeg.probe_info(out), expected_s=3.0)


@pytest.mark.parametrize(
    ("height", "cap"), [(360, 3_000_000), (480, 3_000_000), (720, 5_000_000), (1080, 8_000_000)]
)
def test_bitrate_is_capped_by_source_height(height: int, cap: int) -> None:
    assert video_bitrate(10, height) == cap
    assert video_bitrate(170, height) <= cap  # long clips still get the Telegram budget
```

Move the two `_re`/`_subprocess` imports to the top as `import re` and `import subprocess`, and use those names.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest -q tests/stages/test_render.py -k "lufs or capped"`
Expected: FAIL. The loudness test fails its ±1.5 assert, because the output stays around -34. The bitrate tests fail with `TypeError: video_bitrate() takes 1 positional argument but 2 were given`.

- [ ] **Step 3: Implement**

In `src/clipforge/stages/render.py`:

```python
STAGE_VERSION = "3"  # 3: loudnorm -14 LUFS, bitrate capped by source height
LOUDNORM = "loudnorm=I=-14:TP=-1.5:LRA=11"  # EBU R128, the social-platform norm (ADR-20)
HEIGHT_CAPS = ((480, 3_000_000), (720, 5_000_000))  # source height -> max video b/s


def video_bitrate(duration_s: float, source_height: int = 1080) -> int:
    budget = TARGET_BYTES * 8 / duration_s - AUDIO_BPS
    cap = next((bps for h, bps in HEIGHT_CAPS if source_height <= h), MAX_VIDEO_BPS)
    return int(max(MIN_VIDEO_BPS, min(cap, budget)))
```

In `run()`:
- change `bitrate = video_bitrate(spec.duration_s)` to `bitrate = video_bitrate(spec.duration_s, spec.source.height)`;
- in the ffmpeg args, put `"-af", LOUDNORM,` right before `"-c:a", "aac",`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest -q tests/stages/test_render.py`
Expected: PASS, including the existing `test_bitrate_keeps_every_clip_under_the_telegram_limit`, which calls `video_bitrate(duration)` with the 1080 default.

- [ ] **Step 5: Full check**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"`
Expected: all clean, all pass.

- [ ] **Step 6: Checkpoint**

Files: `src/clipforge/stages/render.py`, `tests/stages/test_render.py`.

---

### Task 2: Captions: hook title card, title key word (`keywords_v2`) and caption pop

**Files:**
- Create: `prompts/keywords_v2.md`
- Modify: `prompts/metadata.json`, `src/clipforge/models.py` (`KeywordsReply`), `src/clipforge/stages/captions.py`
- Test: `tests/stages/test_captions.py`, `tests/test_prompts.py`

**Interfaces:**
- Consumes: the existing `CaptionsDeps(llm, prompt, settings)`, `chunk_words`, `clip_words`, `_clean`, `_limit`.
- Produces:
  - `KeywordsReply.title_keyword: int | None = None`;
  - `KEYWORDS_PROMPT = "keywords_v2"`, `TITLE_S = 3.0`, `TITLE_MAX_WORDS = 10`, `POP` (the tag string);
  - `@dataclass(frozen=True) Emphasis(words: frozenset[int] = frozenset(), title_word: int | None = None)`;
  - `@dataclass(frozen=True) TitleCard(words: tuple[str, ...], key: int | None, end: float)`;
  - `title_words(title: str) -> tuple[str, ...]`;
  - `pick_keywords(ctx, deps, words, chunks, title: tuple[str, ...] = ()) -> Emphasis`;
  - `build_ass(chunks, keywords: frozenset[int] | set[int] = frozenset(), title: TitleCard | None = None) -> str`;
  - `captions.STAGE_VERSION = "3"`.

- [ ] **Step 1: Write the prompt and register it**

`prompts/keywords_v2.md`:

```markdown
---
version: keywords_v2
model_default: claude-haiku-4-5
output: json
---

You pick the words to emphasize in the burned-in captions and the on-screen title of a short vertical video (TikTok, Instagram Reels, YouTube Shorts). Emphasized words are shown in color, so viewers catch the idea at a glance.

## Input
The clip's spoken words, one per line as `<index> <WORD>`. Language: {language}

{words}

The on-screen title, one word per line as `T<index> <WORD>`:

{title}

## What to pick
- Caption words: the words that carry the meaning (key nouns, strong verbs, names, numbers, surprising or emotional words). Never filler or function words (the, a, is, and, to, of, de, que, el, la, y...). At most {max_keywords} in total, spread across the clip, never two words next to each other. Fewer is better than weak picks.
- Title word: the single most striking word of the title, or null if there is no title.

## Output
Return only this JSON object, with no prose and no code fences:

{"keywords": [<index>, ...], "title_keyword": <title index or null>}

Use the indices exactly as given (title indices without the T), most important caption words first.
```

Add to `prompts/metadata.json`:

```json
  "keywords_v2": {
    "released": "2026-09-28",
    "model_default": "claude-haiku-4-5",
    "notes": "keywords_v1 plus one key word for the on-screen hook title (ADR-20)."
  }
```

- [ ] **Step 2: Write the failing tests**

In `tests/stages/test_captions.py`:
- Change the existing `pick_keywords` assertions to compare `.words`: `== {2, 4, 10}` becomes `.words == {2, 4, 10}`, `== set()` becomes `.words == frozenset()`, `== {4}` becomes `.words == {4}`. In the density test, use `picked = pick_keywords(...).words`.
- In `test_build_ass_one_event_per_chunk_lower_and_white`, change `events[0].endswith(",HELLO WORLD")` to `events[0].endswith(POP + "HELLO WORLD")`.
- In `test_build_ass_colors_only_the_keywords`, expect `POP + "THE {\\c&H0000FFFF&}OCEAN{\\c&H00FFFFFF&}"`, and the same for the second event.
- In `test_ass_control_characters_are_stripped`, count `{` only after removing the `POP` prefix: `text.removeprefix(POP).count("{") == 2`.
- Change `_keywords(*indices)` to also accept a title index: `def _keywords(*indices: int, title: int | None = None) -> str: return json.dumps({"keywords": list(indices), "title_keyword": title})`.

Then append:

```python
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
```

Add `POP`, `TITLE_MAX_WORDS`, `TitleCard` and `title_words` to the `clipforge.stages.captions` import.

Append to `tests/test_prompts.py`:

```python
def test_load_keywords_v2() -> None:
    prompt = load_prompt("keywords_v2", PROMPTS)
    assert prompt.placeholders == {"language", "words", "max_keywords", "title"}
    assert "title_keyword" in prompt.render(
        language="en", words="0 HELLO", max_keywords="1", title="T0 HI"
    )
```

- [ ] **Step 3: Run them to verify they fail**

Run: `uv run pytest -q tests/stages/test_captions.py tests/test_prompts.py`
Expected: FAIL, `ImportError: cannot import name 'POP' from 'clipforge.stages.captions'`. `test_load_keywords_v2` passes already, because Step 1 wrote the prompt. That's expected: it checks a file, not code.

- [ ] **Step 4: Implement**

`src/clipforge/models.py`, class `KeywordsReply`, add:

```python
    title_keyword: int | None = None  # keywords_v2: index into the title's words
```

`src/clipforge/stages/captions.py`:
- Set `STAGE_VERSION = "3"  # 3: hook title card + caption pop (ADR-20)` and `KEYWORDS_PROMPT = "keywords_v2"`.
- Add the constants and types:

```python
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
    return tuple(t for t in (_clean(x).upper() for x in title.split()) if t)[:TITLE_MAX_WORDS]
```

- Add a `Title` style line to `_HEADER`, right after the `Style: Default,...` line:

```
Style: Title,{FONT},86,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,7,0,8,90,90,230,1
```

`_clean` must be defined above `title_words` (it already sits above `build_ass`; place the new code after it).

- Replace `build_ass`:

```python
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
```

This is exact source: `f"{{\\c{KEYWORD}}}"` writes `{\c&H0000FFFF&}`, as in the existing `build_ass`.

- Change `_parse_keywords` to also validate the title index:

```python
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
```

- In `pick_keywords`, add `title: tuple[str, ...] = ()` to the signature and return `Emphasis`:
  - `if not words: return Emphasis()`;
  - render the prompt with `title="\n".join(f"T{i} {word}" for i, word in enumerate(title)) or "(no title)"`;
  - on success, `picked, title_word = _parse_keywords(reply.text, len(words), len(title))`, then `return Emphasis(frozenset(_limit(picked, chunks, len(words))), title_word)`;
  - on giving up, `return Emphasis()`.
- In `run()`, inside `compute`:

```python
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
```

Add `"title": spec.candidate.title` to the captions cache-key dict, because the output depends on it now.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest -q tests/stages/test_captions.py tests/test_prompts.py tests/stages/test_render.py tests/stages/test_pipeline_e2e.py`
Expected: PASS. The e2e fake LLM routes on `"emphasize"` in the prompt, and v2 contains it. Render's burn-in band test still passes: the title sits at the top, outside the measured caption band.

- [ ] **Step 6: Full check**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"`
Expected: all clean, all pass.

- [ ] **Step 7: Checkpoint**

Files: `prompts/keywords_v2.md`, `prompts/metadata.json`, `src/clipforge/models.py`, `src/clipforge/stages/captions.py`, `tests/stages/test_captions.py`, `tests/test_prompts.py`.

---

### Task 3: Docs, deploy, real check

**Files:**
- Modify: `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `ROADMAP.md`

- [ ] **Step 1: Docs**

- `docs/ARCHITECTURE.md`, "Phase 1 stage details":
  - **Captions bullet:** append "A hook title card, the LLM's `title` (≤ 10 words, uppercase), is shown top-center for the first 3 s with a 0.3 s fade, and its key word, chosen in the same `keywords_v2` call, is yellow. Every caption line pops in, from 110% to 100% over 0.1 s."
  - **Render bullet:** append "Audio is normalized to -14 LUFS (`loudnorm`, TP -1.5, LRA 11). The video bitrate is also capped by the source height: ≤ 480 p at 3 Mb/s, ≤ 720 p at 5 Mb/s."
- `docs/DECISIONS.md`, add:

```markdown
## ADR-20: Retention polish (loudness, hook title, caption pop, bitrate by source)
Date: 2026-09-28 · Status: Accepted
Context: The owner posts clips to grow their own channels, so retention and a recognizable style matter most. Clips had uneven loudness, no on-screen hook, static captions, and 8 Mb/s video even for 360 p sources, which made 30 clips about 1.2 GB on a slow downlink.
Decision: The render encode normalizes audio to -14 LUFS (single-pass `loudnorm`). The video bitrate is capped by the source height (3/5/8 Mb/s at ≤480/≤720/above). The captions `.ass` gains a hook title card: the highlights `title`, top-center, first 3 s, one yellow key word chosen by the same per-clip LLM call as the caption key words (`prompts/keywords_v2.md`). Every caption line pops in, from 110% to 100% over 100 ms.
Consequences: No new API calls, since the title word shares the keywords call. Clips from low-res sources are much smaller. The captions and render cache versions move to 3, so re-cuts re-render.
```

- `ROADMAP.md`:
  - Phase 3: add `- [x] Retention polish: -14 LUFS audio, hook title card, caption pop, bitrate by source (ADR-20)`.
  - "Later / ideas": add `- Sub-projects from the 2026-09-28 brainstorm: speaker-aware framing + split screen for single-camera podcasts; silence/filler removal (pacing)`.

- [ ] **Step 2: Full check, deploy, re-cut**

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q -m "not gpu and not slow"
uv run modal deploy src/clipforge/app.py
uv run clipforge clip "videos/billy_carton-Koa_smith.mp4" --again --min-score 0.87
```

`--min-score 0.87` gives about 11 clips, so the owner's slow download stays short.

Expected: the job is done, and the clips download into `videos/out/billy_carton-Koa_smith-4/`.

- [ ] **Step 3: Real check**

For one delivered clip:
- save a frame at 1.0 s (the title should be visible) and one at 4.0 s (no title), and look at both with the Read tool;
- run `ffmpeg -i <clip> -af ebur128 -f null -` and check the integrated loudness is about -14 LUFS;
- compare `du -sh` of the new folder with an equal number of clips from `-3/`.

Report the three results to the owner.

- [ ] **Step 4: Checkpoint**

Files: `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `ROADMAP.md`.
