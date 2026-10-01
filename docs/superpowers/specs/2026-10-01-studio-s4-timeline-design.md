# S4: Timeline renderer, design

Date: 2026-10-01 · Card: [006](../../cards/006-s4-timeline.md) · Branch: `s4/timeline` · Status: **approved 2026-10-01** (owner: `assets` out of the render key; ADR-47 two-pass everywhere)
Implements ADR-31 (accepted). Proposes ADR-47 (§6; the owner chose two-pass everywhere, for the coordinator to write into DECISIONS.md). Action card: docs/studio/06 §D "S4".

## 1. Goal and success criteria

One renderer for every producer: a `Timeline` contract is the only input to `render` (ADR-31).

- **Clips move onto it first, with identical output properties.** Resolution 1080x1920, fps, codecs, pixel format, stream counts, duration within one frame, size under 50 MB, loudness -14 LUFS ±1. All are asserted with ffprobe and ebur128, never on bytes.
- **A synthetic Timeline renders correctly.** It has stills (one with Ken Burns), a narration track and a music bed ducked under the narration. It renders at 1080x1920, under 50 MB, at -14 LUFS ±1.
- **Loudness normalization becomes two-pass** (06 §S4 action 4), as proposed in ADR-47 (§6).
- `scripts/check.sh` is green.

Assumptions (not in the card):
- Nothing produces stills, narration or music yet: S5 (media servers) and S6 (story producer) will. S4 only makes the renderer able to play them, and the fixture uses ffmpeg-generated media.
- Smoothed tracking and diarization stay out of scope (ROADMAP Phase 3).

## 2. Approaches

| | Approach | For | Against |
|---|---|---|---|
| **A (chosen)** | **One ffmpeg encode per Timeline.** Each media file is one input, seeked accurately. Visual segments are trimmed, framed to 1080x1920, concatenated, and get the ASS overlay burned in. Audio tracks are mixed with ducking, then loudnorm runs, all in the same run. | One encode, so no generation loss. A clip Timeline produces today's exact video filtergraph. Matches today's speed. | The graph builder is the most involved code in the change. |
| B | One intermediate file per segment, then concat and mux | Simple graphs | Every segment is encoded twice; slower; clips are no longer identical |
| C | Keep the clip render and add a second renderer for Timelines | No risk to clips | Ruled out by ADR-31: the two would drift apart in captions, loudness and size limits |

## 3. Contract (`models.py`, changed first: rule 2)

```python
class KenBurns(Contract):
    zoom_from: float = Field(1.0, ge=1.0)
    zoom_to: float = Field(1.15, ge=1.0)
    focus_from: tuple[float, float] = (0.5, 0.5)   # the frame point kept centered, as fractions
    focus_to: tuple[float, float] = (0.5, 0.5)

class VideoSegment(Contract):                       # a piece of a video file
    type: Literal["video"] = "video"
    kind: Literal["source", "broll", "talking_head"]
    path: str                                       # relative to JOBS_ROOT
    media_hash: str | None = None                   # content hash when known (clips: source_hash)
    width: int; height: int                         # display size after rotation
    in_s: float = Field(ge=0)                       # media time at the segment start
    start: float = Field(ge=0); end: float          # timeline time [start, end)
    fit: Literal["crop", "cover", "blur"]
    box: CropBox | None = None                      # set iff fit == "crop"

class StillSegment(Contract):                       # an image held on screen
    type: Literal["still"] = "still"
    path: str; media_hash: str | None = None
    width: int; height: int
    start: float = Field(ge=0); end: float
    fit: Literal["cover", "blur"] = "cover"
    ken_burns: KenBurns | None = None

VisualSegment = Annotated[VideoSegment | StillSegment, Field(discriminator="type")]

class AudioTrack(Contract):
    kind: Literal["source", "narration", "music"]
    path: str; media_hash: str | None = None
    in_s: float = Field(0.0, ge=0)
    start: float = Field(ge=0); end: float          # timeline time
    gain_db: float = 0.0
    duck: bool = False                              # music only: ducked under source + narration

class Subtitles(Contract):                          # captions + hook title card, one ASS file
    ass_path: str
    srt_path: str | None = None

class Timeline(Contract):
    width: int = 1080; height: int = 1920
    fps: int = Field(ge=1, le=60)
    duration_s: float = Field(gt=0)
    visual: list[VisualSegment]                     # contiguous, from 0 to duration_s
    audio: list[AudioTrack] = []                    # each inside [0, duration_s]
    overlay: Subtitles | None = None
    loudness_lufs: float = -14.0
    assets: list[AssetSource] = []                  # licensing is data (ADR-25/30)

class Loudness(Contract):
    input_i: float | None; input_tp: float | None; input_lra: float | None
    mode: Literal["linear", "dynamic", "single_pass", "silent"]

class RenderedVideo(Contract):                      # what render returns, for any producer
    video_path: str; encoder: Literal["h264_nvenc", "libx264"]
    probe: ProbeInfo; loudness: Loudness
```

Validators:
- Visual segments are contiguous (within 1 ms), start at 0 and end at `duration_s`. This is the same rule `CropTrack` uses today.
- `box` is set only when `fit == "crop"`.
- `duck` is only allowed on music.
- Audio tracks lie inside the Timeline.
- Every path is relative, with no `..`, so the job-root rule from ADR-13 holds.

`RenderedClip` keeps its shape (`clip_id`, `spec`, `video_path`, `srt_path`, `encoder`, `probe`). Package, posting, the notifier and the bot don't change.

**Deviations from 02 §2's sketch** (the coordinator updates 02 afterwards):
- There is no `title_card` field. The hook title card stays inside the ASS overlay, built by the shared `captions.build_ass` (owner ruling, 2026-10-01). Every producer that wants the ADR-18/20 look builds its overlay with the same function, so the styling can't drift, and the captions cache and clip output don't change.
- `size: tuple` became `width`/`height`, `duration` became `duration_s`, and `captions: CaptionFiles` became `overlay: Subtitles`. `CaptionFiles` is clip-specific (`clip_id`, `offset_s`).
- The code lives in `stages/` (`render.py` and a new `timeline.py`), not in a `timeline/` package. Render is a stage, and one module is enough until a second producer exists.

## 4. Renderer (`stages/render.py`, `STAGE_VERSION` 3 → 4)

`render.run(ctx, timeline, settings, clip_id=None) -> Stored[RenderedVideo]`

**Cache (ADR-8).** The key is `cache_key("render", "4", [], {"timeline": <canonical JSON of the Timeline without `assets`>})`. `assets` stays on the Timeline for the policy gate (ADR-29) but is left out of the key: licensing doesn't change the output, and a permission edit (S1 rollout, `clipforge source edit`) must not re-render every clip (owner, 2026-10-01). The Timeline has no ids, so a cached render is shared across jobs and ranks, as today. The key also leaves out a media `path` wherever `media_hash` is set, and the overlay's `srt_path`: neither changes the output, and a clip's path holds the ingest key, which follows the URL, not the bytes (review at CP2, the plan's Task 5). `media_hash` makes source content part of the key: clips set it to `source_hash`, and generated assets live in key-addressed cache directories. `timeline.json` is written next to `clip.mp4` for debugging.

**Inputs.**
- Each distinct video or audio file is one input: `-ss <min in_s> -t <span> -i <path>`, seeked accurately as today.
- A file used for both picture and sound (a clip's source) is opened once.
- A still without Ken Burns is `-loop 1 -framerate <fps> -t <dur> -i`. A still with Ken Burns is a single image driven by `zoompan`.

**Video graph.**
- Each segment is trimmed out of its input (`trim`, `setpts=PTS-STARTPTS`) and framed to `width`x`height`:
  - `crop`: today's `_crop`, crop by the box, then a lanczos scale.
  - `cover`: scale to fill, center crop.
  - `blur`: today's `_blur`.
  - Ken Burns: `zoompan` on a 2x pre-scaled cover, with zoom and focus interpolated linearly over the segment's frames.
- Segments are concatenated and the overlay is burned in with `ass=` and the fonts dir.
- The three clip cases produce exactly today's strings:
  - one `crop` segment over the whole range gives today's `center` graph;
  - one `blur` segment gives today's `blur_fallback` graph;
  - several segments from one input give today's `split`/`trim`/`concat` graph.

**Audio graph.**
- One `source` track over the whole Timeline at 0 dB is exactly today's chain, `[0:a:0]` → loudnorm.
- Otherwise, each track is trimmed, given its `gain_db`, delayed to its `start` (`adelay`), and formatted to 48 kHz stereo.
- When a ducked music track exists, the voice tracks (source and narration) are mixed and split. One copy feeds `sidechaincompress` (threshold 0.03, ratio 8, attack 20 ms, release 400 ms; the values used in the §6 measurements) on the music. All tracks are then mixed with `amix normalize=0`, padded or trimmed to `duration_s`, and passed to loudnorm.
- With no audio tracks, the output gets `anullsrc` (48 kHz stereo) and no loudnorm (mode `silent`), so every output has one AAC stream, as platforms expect.

**Two-pass loudness (ADR-47).**
- Pass 1 runs the same inputs and the audio graph only (`-vn`) into `-f null`, with `loudnorm=…:print_format=json`. It takes 1.9 s for a 32 s clip seeked into a 1-hour source.
- Pass 2 is the full encode with `measured_I/TP/LRA/thresh`, `offset` and `linear=true`. ffmpeg itself falls back to dynamic mode when linear gain would break the true-peak limit.
- If pass 1 measures silence (`-inf`) or its JSON can't be parsed, render logs a warning and uses today's single-pass filter. Loudness never fails a render.
- The mode and the measured input values go into `RenderedVideo.loudness`.

**Bitrate (ADR-20, generalized).**
- The cap is set by the largest short side among the visual media. With one source, that is today's rule exactly; generated 1080x1920 stills count as 1080, so 8 Mb/s.
- The Telegram budget uses `duration_s`.
- `fps` comes from the Timeline. The clip builder sets it to today's `min(60, round(source fps) or 30)`.

**Unchanged:** libx264 `veryfast` CRF 21, `-maxrate`/`-bufsize`, yuv420p, AAC 128 kb/s 48 kHz stereo, `+faststart`, the >50 MB `PermanentError`, the font warning, and the `StageCost` (wall seconds, now including pass 1).

## 5. Clips onto the Timeline (`stages/timeline.py`, pure)

`for_clip(spec, track, captions, permission, credit=None) -> Timeline` (the permission and credit fill `assets`):
- `CropTrack` `center` gives one `VideoSegment(kind="source", fit="crop", box)` over `[0, duration]` with `in_s = spec.start`.
- `blur_fallback` gives one `fit="blur"` segment.
- `tracked` gives one segment per `CropSegment`, with `in_s = spec.start + seg.start`.
- The source audio becomes one `AudioTrack(kind="source", in_s=spec.start)` over the clip.
- The overlay is `Subtitles(captions.ass_path, captions.srt_path)`. The single asset is `AssetSource(kind="source_video", license=<permission>)`.

`StageRunner.clip`: reframe → captions → `timeline.for_clip` → `render.run` → wrap into `RenderedClip(clip_id, spec, video_path, srt_path, encoder, probe)`.
- `steps.clip_step` already rebinds `clip_id` and `spec` on cached results, so it doesn't change.
- Reframe and captions keep their versions and caches.

## 6. Proposed ADR-47: two-pass loudness normalization

**Context.** ADR-20 normalizes with a single-pass `loudnorm` (I=-14, TP=-1.5, LRA=11). Single pass estimates loudness on the fly and applies dynamic gain. Two-pass measures first, then applies one linear gain. Mixed Timelines (narration over a ducked music bed) are the case two-pass is meant for, since a constant gain keeps the ducking envelope intact. 06 §S4 asks for it.

**Measurements** (2026-10-01, ffmpeg 6.1.1, local; output encoded AAC 128 kb/s like render; integrated loudness, true peak, LRA from `ebur128=peak=true`):

| Input | Before (LUFS / dBTP / LU) | Single pass | Two pass | Pass-2 mode |
|---|---|---|---|---|
| Real clip_01 (Billy Garton, 31.7 s) | -16.2 / -1.3 / 3.4 | **-14.5** / -1.0 / 3.3 | **-14.2** / -1.1 / 3.3 | dynamic |
| Real clip_02 | -15.9 / -1.2 / 4.4 | -14.5 / -1.2 / 4.1 | -14.2 / -0.9 / 4.0 | dynamic |
| Real clip_03 | -15.3 / -1.1 / 5.7 | -14.2 / -1.0 / 5.3 | -14.1 / -1.3 / 5.3 | dynamic |
| Real clip_04 | -15.8 / -1.2 / 4.9 | -14.2 / -1.2 / 4.4 | -14.1 / -1.2 / 4.4 | dynamic |
| Real clip_05 | -15.8 / -1.3 / 3.2 | -14.5 / -1.3 / 3.0 | -14.1 / -1.2 / 3.0 | dynamic |
| Synthetic mix (gated narration -8 dB over a ducked pink-noise + 110 Hz bed, 30 s) | -30.4 / -23.9 / 0.7 | **-14.1** / -7.5 / 0.7 | **-14.0** / -7.5 / 0.7 | linear |
| Synthetic, hard (loud bed, narration only in the first 10 s) | -25.8 / -17.0 / 0.8 | -13.8 / -4.9 / 0.6 | -14.0 / -5.2 / 0.8 | linear |

The real clips are the source ranges of the first five clips of the latest Billy Garton job (`metadata.json` start/end), cut from the local source file. The cached renders on the Volume are already normalized, so the pre-render range is the honest input.

**Findings.**
- **Single pass already lands within ±1 LU everywhere**, including both mixed fixtures (-14.5 to -13.8). Two-pass tightens that to -14.2 to -14.0, a gain of 0.1–0.3 LU.
- **On real podcast clips, two-pass doesn't run linear.** The sources already peak near -1.2 dBTP, so the linear gain would break the -1.5 limit, and ffmpeg falls back to dynamic mode with better-measured inputs. Linear mode, the reason to do two passes, only applies to the mixed Timelines.
- **True peak after the AAC encode is -0.9 to -1.3 dBTP in both modes.** That is over the -1.5 target, because the AAC encode overshoots, and the issue is the same today. I'm not changing it in S4. If a platform ever flags clipping, TP=-2.0 is the knob.
- Pass 1 costs about 2 s of CPU per 30 s clip, under $0.0001.

**Decision (proposed ADR; the owner chose this option on 2026-10-01).** Every Timeline render, clips included, measures first and normalizes in a second pass with `linear=true`. Silence or an unparseable measurement falls back to today's single pass. This replaces ADR-20's "single-pass `loudnorm`"; ADR-20's targets (-14 LUFS, TP -1.5, LRA 11) are unchanged.

**Alternative (not chosen; the owner picked two-pass everywhere on 2026-10-01).** The numbers say single pass is good enough for clips (within 0.5 LU). Keeping single pass for clips would save 2 s of CPU per clip and nothing else. I recommend two-pass everywhere anyway: one code path, and the same behavior for clips and mixes. If you'd rather keep single pass for clips, the Timeline gets `loudness_passes: Literal[1, 2]`; the clip builder sets 1 and the renderer branches.

**Consequences.** Mixed Timelines get exact, linear normalization that leaves the ducking intact. Clips change by 0.1–0.3 LU (not audible). The audio is decoded once more per render. `RenderedVideo.loudness` records what happened.

## 7. What the render `STAGE_VERSION` bump does downstream

`render.STAGE_VERSION` "3" → "4". It must bump: the render input changed shape, and the audio chain changed (ADR-8).

- **Every clip re-renders on its next job.** The old `cache/render/<key>/` entries are never matched again, so each re-cut re-encodes its clips: a few CPU seconds per clip, about $0.0003 at today's rates. The transcript, highlights, reframe and captions caches are reused, since their versions don't change.
- **Already delivered clips don't change.** Packaged clips, `job.zip`, posting items and their Telegram messages keep their files. Nothing re-renders by itself.
- **`producer_version` changes (ADR-43).** It hashes the sorted `STAGE_VERSIONS` (`runner.STAGE_VERSIONS` includes render), so new clip items get `clips:<new hash>`; it was `clips:14fcf790` at the pause. Items already queued keep the version they were stamped with.
- **Under ADR-29, a new producer version starts in `review`,** so once S2's review tiers exist, the next clips start in review. Before S2, every clip already goes through the assisted Telegram flow by hand, so nothing visible changes now.
- **Rollback:** revert the PR. The v3 cache entries are still on the Volume, so reverted jobs hit them again.

## 8. Errors (ADR-15)

- Timeline validation errors are producer bugs. They are raised at construction, in the producer's own step. The clip builder can't build an invalid Timeline from a valid `CropTrack` (tested).
- ffmpeg failures stay `FfmpegError`, which is transient and retried twice, as today. A missing media file surfaces as an ffmpeg error (Volume reload lag is the usual cause), also retried.
- Over 50 MB is a `PermanentError`, as today.
- A failed loudness measurement isn't an error (§4).
- Error messages name the stage and kind, never file contents or URLs (rule 8, `sanitize`).

## 9. Cost, security, ops

- **Cost (rule 7):** render records its wall seconds as today. There is no GPU and no LLM. Build and verify stay well under the $2 cap: local ffmpeg only, plus at most one `app.py::smoke` run (about $0.01) after your OK.
- **Security:** no new secrets, routes or inputs from users. Every Timeline path is relative and checked against `..`, and render resolves paths through `ctx.path`, so served and read files stay under `/jobs`. `filter_path` still rejects unsafe characters in paths used inside the filtergraph.
- **Modal image:** the CPU image installs Debian's `ffmpeg`. `amix normalize` needs ffmpeg 4.4 or later; `sidechaincompress`, `zoompan` and `loudnorm` JSON are older. Verify checks the image's ffmpeg version through `app.py::doctor` before the PR.

## 10. Tests (fast unless marked)

1. Contract: every validator in §3 (contiguity, the box/fit rule, duck only on music, relative paths), and a JSON round-trip of the discriminated union.
2. `timeline.for_clip` for center, blur and tracked: segment boundaries and `in_s`, the audio track, overlay paths, the asset.
3. The clip video graphs equal today's `filter_graph` output exactly for center, blur and tracked (golden strings captured from the v3 code before it changes).
4. Ported clip renders (center, blur, rotated, tracked, 12 segments, cached, captions burned in, quiet source at -14 ±1.0). All are ffprobe-asserted: 1080x1920, fps, h264/yuv420p, aac, one stream each, duration within one frame, under 50 MB.
5. A synthetic Timeline, with fixture media generated by ffmpeg in `tmp_path`: two stills (one Ken Burns, one blur fit), 6 s each, a gated-sine narration and a pink-noise music bed with `duck=True`, plus a captions overlay. It must be 1080x1920, under 50 MB, -14 ±1.0 LUFS, and `loudness.mode == "linear"`.
6. Ducking: the music's RMS during narration is at least 6 dB lower than in the pauses, measured on the mix.
7. Loudness fallbacks: a silent Timeline renders with an AAC stream and mode `silent`; unparseable pass-1 output falls back to single pass (ffmpeg mocked).
8. Bitrate: today's tests, plus the cap from the largest short side over several media.
9. Cache: the same Timeline gives no ffmpeg calls on the second run; a different `media_hash` gives a different key; two Timelines that differ only in `assets` share one key.

## 11. Rollout

- No migration, no Dict keys and no settings.
- The owner deploys with `scripts/deploy.sh` after merge, outside the blackout.
- The first job after the deploy re-renders its clips (§7).
- An optional smoke run: `uv run modal run src/clipforge/app.py::smoke`.

## 12. Docs (this card's scope)

- ARCHITECTURE: the render row and "Phase 1 stage details: Render" (Timeline input, two-pass loudness), and the stages table (render input `Timeline`).
- CLAUDE.md layout: `stages/timeline.py`.
- Decision-log rows from #340.

**Out of scope, for the coordinator:**
- ADR-47 into DECISIONS.md, and the ADR-20 "updated by ADR-47" note;
- 02 §2's Timeline sketch (the title card deviation);
- the ticks in ROADMAP and 04;
- 03's measured numbers.

## 13. Out of scope

- Talking-head and b-roll generation (S5).
- Producers other than clips (S6+).
- GPU encoding.
- Caption style presets.
- Smoothed tracking.
- Changing the TP target.
