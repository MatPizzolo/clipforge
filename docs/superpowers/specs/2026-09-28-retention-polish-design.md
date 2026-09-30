# Retention polish: loud-normalized audio, hook title, caption pop, lighter files

Date: 2026-09-28 · Status: Accepted, implemented and deployed · ADR: 20 · Sub-project 1 of 3 from the "professional clips" brainstorm (2: speaker-aware framing, 3: pacing)

## 1. Goal and constraints

**Outcome.** Every clip is built to hold viewers of the owner's own channels:
- an even, platform-standard loudness;
- a hook headline in the first seconds;
- captions that "pop" in;
- files sized for the source instead of the maximum.

**Decided during brainstorming (2026-09-28)**

| Topic | Decision |
|---|---|
| Audio | EBU R128 loudness normalization to **-14 LUFS** integrated, true peak **-1.5 dBTP**, LRA **11**, single-pass `loudnorm` in the render encode |
| Hook title text | The highlights LLM's existing `title` field ("on-screen hook text, max 8 words"), uppercase |
| Hook title style | Style **B**: Anton, white, 7 px black border like the captions, **one key word in yellow**, top-center |
| Hook title timing | **First 3 s** of the clip (or the whole clip if shorter), with a 0.3 s fade-out |
| Title key word | Chosen by the LLM in the same per-clip call that picks the caption key words (a new prompt version, `keywords_v2`). If the reply is invalid, the title is all white. |
| Caption pop | Each caption line starts at 110% scale and settles to 100% over 100 ms |
| File size | Video bitrate capped by the source height: ≤ 480 → 3 Mb/s, ≤ 720 → 5 Mb/s, otherwise 8 Mb/s (the Telegram 45 MB rule still applies on top) |

**Constraints**
- One encode per clip, as now. The title lives in the same `.ass` as the captions.
- Prompts are files (rule 4). `keywords_v1` stays as released; `keywords_v2` is new and registered in `prompts/metadata.json`.
- LLM output is validated, with one retry carrying the error (rule 5). A failure never fails a clip (ADR-18).
- The output contract is unchanged: 1080x1920, h264/yuv420p, AAC 48 kHz stereo, A/V within 50 ms, under 50 MB.

## 2. Components

| Unit | Change |
|---|---|
| `prompts/keywords_v2.md` (new) | Same task as v1, plus a title section: the title's words listed as `T<index> <WORD>`. The output is `{"keywords": [<index>...], "title_keyword": <index> \| null}`. |
| `models.py` | `KeywordsReply` gains `title_keyword: int \| None = None` (tolerant of v1-style replies) |
| `stages/captions.py` | `KEYWORDS_PROMPT = "keywords_v2"`. `pick_keywords(...) -> Emphasis(words: set[int], title_word: int \| None)`; validation rejects a title index out of range. `build_ass(chunks, keywords, title: TitleCard \| None)` adds a `Title` style (Anton 86, white, outline 7, alignment 8, MarginV 230) and one `Title` event from 0 to `min(3.0, clip end)` with `{\fad(0,300)}`, with the key word wrapped in yellow. Every caption event starts with `{\fscx110\fscy110\t(0,100,\fscx100\fscy100)}`. `run()` builds the title from `spec.candidate.title` (cleaned of ASS control characters, uppercase). `STAGE_VERSION = "3"`. The cache key already has the prompt version. |
| `stages/render.py` | `-af loudnorm=I=-14:TP=-1.5:LRA=11` before the AAC encode. `video_bitrate(duration_s, source_height)` applies the height cap. `STAGE_VERSION = "3"`. |
| Docs | ARCHITECTURE (captions + render details), ADR-20, ROADMAP (the Phase 3 caption style line, plus a new "Retention polish" line) |

**Title layout.**
- Top-center with MarginV 230 on 1920 (12% from the top, below the status-bar area).
- ASS wraps it automatically (`WrapStyle: 0`) within 90 px side margins.
- 8 words of Anton 86 fit on 2–3 lines.

## 3. Error handling

| Failure | Result |
|---|---|
| The keywords reply is invalid twice | No yellow words anywhere (captions and title all white); warning logged, as ADR-18 does today |
| `title_keyword` out of range, or not an int | Counts as an invalid reply, so it's retried once with the error |
| Empty title (the LLM returned "") | No title event |
| `loudnorm` on silence or very short audio | ffmpeg handles it: the output is silent and still valid, and the existing A/V checks cover it |

## 4. Testing

- **captions:**
  - the title event exists from 0 to 3.00 s with `\fad(0,300)` and the yellow key word;
  - a clip shorter than 3 s ends the title at the clip end;
  - an invalid reply gives an all-white title;
  - a `title_keyword` out of range is retried;
  - every caption event carries the pop tags;
  - the `keywords_v2` prompt renders the title words;
  - the `.ass` still parses in a real render (the existing burn-in band test).
- **render:**
  - the output's integrated loudness, measured with ffmpeg `ebur128`, is within ±1.5 LU of -14 for a quiet sine source at -30 dBFS;
  - `video_bitrate` for heights 360/480/720/1080;
  - `assert_vertical_clip` still passes.
- **Real check:**
  - `clipforge clip --again` on the podcast;
  - one frame at 1 s with the title and one at 4 s without it;
  - the measured loudness of one delivered clip;
  - the total output size compared with the previous re-cut.

## 5. Out of scope
- Speaker-aware framing and split screen (sub-project 2).
- Silence and filler removal (sub-project 3).
- Per-channel style presets and branding (logo, end card).
