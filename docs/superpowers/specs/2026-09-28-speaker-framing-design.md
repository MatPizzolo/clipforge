# Speaker-aware framing: cut to whoever is talking in two-person shots

Date: 2026-09-28 · Status: Accepted, implemented and deployed · ADR: 21 · Sub-project 2 of 3 from the "professional clips" brainstorm (1: retention polish, done; 3: pacing)

## 1. Goal and constraints

**Outcome.** In a shot that shows two (or more) people, as in a single-camera podcast or the wide shots of a multi-camera one, the 9:16 clip frames whoever is talking and cuts to the other person when the turn changes, like a virtual multi-camera edit. Today reframe frames the largest face, so it stays on one person even while the other one talks.

**Decided during brainstorming (2026-09-28)**

| Topic | Decision |
|---|---|
| Wide-shot layout | **Cut to the speaker.** No split screen. |
| Who is speaking | **Option C:** visual mouth motion now; audio diarization (pyannote) later, only if real footage shows wrong switches. The interface is "which seat said each word", so diarization can replace the visual step without touching turns or render. |
| Switch style | Hard cut, never a pan. A switch lands in the middle of the pause between two words, never mid-word. |
| Minimum turn | **2.0 s.** Shorter turns ("yeah", "right") merge into a neighboring turn. |
| People close together | If every seat fits inside one 9:16 crop, frame the group and never switch. |
| Test footage | `videos/billy_carton-Koa_smith.mp4`, which has both one-person shots and wide shots of both people. |

**Constraints**
- Stage modules never import Modal (rule 1). Per-clip work only, on the clip's time range (rule 6).
- No new dependencies, no API calls, no new tokens. It runs on the CPU in `clip_step`.
- A failure never fails a clip. The fallback is today's framing (largest face per shot), and a fallback is never cached (`_Degraded`, ADR-19).
- Output contract unchanged: `CropTrack(mode="tracked", segments=[...])`, contiguous segments from 0 to the clip duration. Render is untouched.

## 2. Behavior

- **Where it applies.** `auto` reframe on landscape sources (`uses_tracking`), for each shot from the existing cut detection. One-seat shots, shots without faces, forced `center`/`blur`, and vertical or near-square sources behave exactly as today.
- **Seats.** The existing 3 samples per shot (at 25/50/75%) now keep **all** faces at least 4% of the sample width, not just the largest. Faces from different samples are the same seat when their centers are closer than the wider face's width. A seat must appear in at least 2 of the 3 samples. Its box is the median of its detections.
- **Group fits in one crop.** If the span from the leftmost seat's left edge to the rightmost seat's right edge, plus 10% of that span as padding, is no wider than the full-height 9:16 crop, the shot gets one crop centered on the span. No switching.
- **Mouth motion.** One ffmpeg call decodes the shot at **10 fps** as 640-px-wide grayscale frames. For each seat, on each pair of consecutive frames:
  - `mouth` = the mean absolute difference inside the mouth patch (x from the left mouth corner − 0.15·w to the right corner + 0.15·w; y from mouth y − 0.10·h to mouth y + 0.15·h, where w and h are the seat's face box);
  - `head` = the same, inside the eye band (the face box's top 45%);
  - score = `max(0, mouth − head)`, so a listener who nods or turns their head doesn't count as talking.
  Patches are clipped to the frame. A patch under 4x4 pixels scores 0.
- **Words to seats.** Each transcript word inside the shot goes to the seat with the highest mean score over the word's time span. It's "unknown" when no frame falls inside the span, when the best score is 0, or when the best is less than **1.2×** the runner-up.
- **Turns.**
  1. Consecutive words with the same seat form a turn. Unknown words join the turn before them (or the next one, at the start of the shot).
  2. While any turn is shorter than 2.0 s (measured first word start to last word end), merge the shortest into its neighbor with the longer duration.
  3. A switch between turns is placed at the midpoint of the gap between the last word of one turn and the first word of the next.
  4. The first turn starts at the shot start (initial silence goes to the first speaker), and the last ends at the shot end.
  5. Each turn becomes a `crop` segment on its seat, using `crop_box(seat cx)`. Neighboring equal segments are merged (`_merge_same`).
- **No usable words.** If a shot has no words, or every word is unknown, the shot uses its largest face (today's behavior). This isn't a degraded result: it's cached.

## 3. Components

| Unit | Change |
|---|---|
| `stages/faces.py` | `Face` gains `mouth_left: tuple[float, float]` and `mouth_right: tuple[float, float]` (YuNet columns 10–13, in sample pixels). |
| `stages/speakers.py` (new) | `Seat` (dataclass: `cx`, `face`, box helpers).<br>`seats(samples: list[list[Face]], min_seen=2) -> list[Seat]`.<br>`fits_one_crop(seats, crop_w) -> bool`.<br>`mouth_motion(video, start, end, seats, size, fps=10) -> Motion` (`times: list[float]`, `scores: ndarray[frames, seats]`), which raises on an ffmpeg failure.<br>`assign_words(words, motion) -> list[int \| None]`.<br>`turns(words, seat_ids, shot_start, shot_end, min_turn=2.0) -> list[Turn] \| None` (`Turn(start, end, seat)`, shot-relative). |
| `stages/reframe.py` | `_segments` handles the three cases per shot (one seat / group fits / speaker turns). `track(ctx, spec, words, detector, settings)`: `words` are the transcript words overlapping the clip, and the cache key adds a hash of their `(start, end)` pairs relative to the clip start. `STAGE_VERSION = "4"`. |
| `stages/runner.py` | `clip()` passes the transcript's words for the clip range to `reframe.track`. |
| Docs | ARCHITECTURE (reframe details, the Phase 3 note), ADR-21, and ROADMAP ("Active speaker selection": the visual part is done, diarization stays open). |

`models.py` and `render.py` don't change.

## 4. Error handling

| Failure | Result |
|---|---|
| The mouth-motion ffmpeg call fails or returns no frames | That shot uses its largest face. The track is degraded and not cached. |
| No words in the shot, or all unknown | The largest face (cached, not degraded) |
| A face seen in only 1 of the 3 samples | Not a seat |
| 3 or more seats | Same logic: each turn goes to whichever seat is talking |
| The shot is shorter than 2 s, or has one turn | One crop on that shot's speaker |
| A mouth patch past the frame edge | Clipped. Under 4x4 px it scores 0. |

## 5. Testing

- **`turns`** (pure):
  - alternating 3 s turns become matching segments;
  - a 1 s "yeah" is merged into its neighbor;
  - each switch lands mid-pause;
  - initial silence goes to the first speaker;
  - all-unknown gives `None`;
  - segments are contiguous and cover the shot exactly;
  - unknown words join the previous turn.
- **`assign_words`**, on a hand-made `Motion`:
  - picks the highest mean;
  - a near-tie (under 1.2×) gives unknown;
  - a word with no frames gives unknown.
- **`seats`**:
  - groups by position;
  - drops a face seen once;
  - keeps two seats apart.
- **`fits_one_crop`**: close faces fit and far faces don't.
- **`mouth_motion`**, on a synthetic 1280x720 4 s video with the real face fixture pasted at two positions. Only the left face's mouth patch flickers (noise) during 0–2 s, and only the right one's during 2–4 s. The left seat must score higher in the first half, and the right seat in the second.
- **`reframe`**:
  - a two-seat shot with words gives 2 crop segments centered on each face;
  - close faces give one centered crop;
  - an ffmpeg failure falls back to the largest face and isn't cached;
  - the cache key changes with word timings.
- **`faces`**: YuNet's mouth corners fall inside the face box (on the existing real-face fixture).
- **Real check:**
  - `clipforge clip --again` on the Billy Carton and Koa Smith video;
  - pick a clip containing a wide shot and save a frame before and after a switch;
  - confirm by eye, against the transcript, that the crop follows the speaker.

## 6. Out of scope

- Audio diarization (pyannote), and speaker labels in the highlights prompt. This is the follow-up if the visual switches are wrong.
- Split-screen layouts.
- Smoothed in-shot tracking (EMA/Kalman) for people who move a lot.
- Silence and filler removal (sub-project 3).
