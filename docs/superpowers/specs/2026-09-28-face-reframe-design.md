# Face-centered reframing per shot

Date: 2026-09-28 · Status: Accepted, implemented and deployed · ADR: 19 · Roadmap: Phase 3 "Scene detection" + "Face tracking" (the smoothed tracking part is out of scope)

## 1. Goal and constraints

**Problem.** The Phase 1 reframe is a fixed center crop. In the owner's podcast (multi-camera, one person per shot, cuts every few seconds), the speaker sits in the left or right third, so the 9:16 center crop cuts them in half or shows the window.

**Outcome.** Each clip is cut at its camera changes. Every shot is framed on the person in it, with the crop fixed for the whole shot and moving only at cuts, the way an editor would do it.

**Decided during brainstorming (2026-09-28)**

| Topic | Decision |
|---|---|
| Two or more people in a shot | Frame the **largest face** (closest to the camera). Active-speaker choice stays in the roadmap. |
| Movement inside a shot | **Fixed per shot**. No smoothed following. |
| Shots without a reliable face | Whole frame over the blurred background (the existing `blur_fallback` look) |
| Detector | OpenCV `FaceDetectorYN` with the YuNet model (MIT, 230 KB, CPU). Checked 2026-09-28: opencv-python-headless 5.0.0 finds the faces in the fixture (score 0.92) and the podcast (0.93). |
| Shot detection | ffmpeg's `select='gt(scene,T)'` with `showinfo` on the clip range. No PySceneDetect dependency. |

**Constraints**
- Reframing must never lose a clip. Any detection failure falls back to one whole-clip blur segment and logs a warning.
- Per-clip work only (CLAUDE.md rule 6). Detection reads only `[spec.start, spec.end]`, at low resolution.
- One encode per clip, as now. The audio stream is untouched, so A/V sync is preserved.
- Stage modules stay Modal-free. The new dependency is `opencv-python-headless` (which brings numpy).

## 2. Components

| Unit | Location | Change |
|---|---|---|
| Contracts | `models.py` | New `CropSegment(start, end, mode: "crop" \| "blur", box: CropBox \| None)`, with times relative to the clip start. `CropTrack.mode` gains `"tracked"`, and `CropTrack.segments: list[CropSegment]` (empty for the other modes). Validation: segments are contiguous, cover `[0, duration]` and are ordered; `crop` requires a box and `blur` forbids one. |
| Shot detection | `stages/shots.py` (new) | `detect_cuts(video: Path, start: float, end: float, threshold: float) -> list[float]` (clip-relative seconds); `segments_from_cuts(cuts, duration, min_len=0.5) -> list[tuple[float, float]]` merges short shots into the previous one |
| Face detection | `stages/faces.py` (new) | `Face(cx, cy, w, h, score)`; `FaceDetector` protocol with `detect(frame: np.ndarray) -> list[Face]`; `YuNetDetector(model_path, score_threshold=0.6)`, lazily importing cv2; `sample_frames(video, times, width=640) -> list[np.ndarray]`, which pipes raw RGB from ffmpeg |
| Reframe | `stages/reframe.py` | `plan(spec)` stays for already-9:16 sources and for forced `center`/`blur`. New `track(ctx, spec, detector, settings) -> Stored[CropTrack]`, cached, which for `auto` on sources wider than 9:16 runs, per segment: sample 3 frames (at 25%, 50% and 75%), take the largest face per frame, take the median center over the frames with a face, then a full-height 9:16 box centered on it and clamped to the frame. With no face in any sample, the segment is `blur`. Any exception gives a single whole-clip `blur` segment plus `log.warning`. |
| Render | `stages/render.py` | `filter_graph` for `tracked`: `split=N`, then per segment `trim=start:end,setpts=PTS-STARTPTS`, then that segment's crop+scale or blur-fit, then `concat=n=N:v=1:a=0`, then `ass`. For a single segment it's the same as today. |
| Runner | `stages/runner.py` | `PipelineStages` gets a `FaceDetector` (YuNet from `settings.models_dir`). `clip()` always calls `reframe.track(...)`. `track` returns `plan(spec)` unchanged when tracking doesn't apply: an already-9:16 source, `reframe=center`/`blur`, or `auto` on a source narrower than 1.2:1 (blur-fit, as now). |
| Config | `config.py` | `models_dir` (the repo's `assets/models`, `/app/assets/models` in the image), `scene_threshold: float = 0.3` |
| Assets | `assets/models/face_detection_yunet_2023mar.onnx` + `LICENSE` (MIT) | new |
| Image | `app.py` | Mount `assets/models` like the fonts. opencv comes in through `uv.lock`. |
| Versions | `reframe.STAGE_VERSION = "2"`, `render.STAGE_VERSION = "2"` | the render cache key includes the track (already true through `mode` + `box`; the segments are added) |

**Where the 9:16 box goes.**
- A source is `W×H`, wider than 9:16. The box is `h = H − H%2`, `w = even(h·9/16)`, `x = clamp(cx − w/2, 0, W − w)` rounded to even, and `y = 0`.
- `cx` comes from detection at 640 px width, scaled back to the source width.

**Detection cost.** Per clip, it's a single ffmpeg pass over the clip range at scene detection resolution (scaled to 320 px wide, `-an`), plus 3 small frames per shot. That's about 2–5 s of CPU for a 45 s clip.

## 3. Error handling

| Failure | Result |
|---|---|
| Scene detection fails (ffmpeg error) | Treat the whole clip as one shot, and continue with face detection |
| The face model fails to load, or cv2 import fails | Whole clip blurred, with a warning in the log. Every clip of the job degrades the same way, and the owner sees it in the output. |
| A frame can't be decoded | That sample counts as "no face" |
| No face in any sample of a shot | That shot is `blur` |
| The source video can't be read at all | Transient error (render would fail too); Modal retries the step |

## 4. Testing

Fast tests use real ffmpeg on synthetic media, as the other stages do.

- **`shots.py`:** a generated video of 3 solid colors × 2 s gives cuts near 2.0 and 4.0 (within 1 frame). `segments_from_cuts` merges a 0.3 s shot into the previous one and covers `[0, duration]`.
- **`faces.py` + `reframe.track`:** faces come from a frame of `tests/fixtures/talking_head_10s.mp4`, since YuNet doesn't detect drawn faces.
  - A generated 16:9 video pastes that face at the left for 2 s, then at the right for 2 s. The result is 2 `crop` segments whose boxes contain each face center.
  - A face at the frame edge gives a box clamped inside the frame.
  - A solid-color shot gives a `blur` segment.
  - A two-face frame (the face pasted at two sizes) frames the larger one.
  - A detector that raises gives one whole-clip `blur` segment and a logged warning.
  - The contract validation rejects gaps, overlaps, a `crop` without a box and a `blur` with one.
- **Render:** a 3-segment track (crop, blur, crop) passes `assert_vertical_clip`: 1080x1920, 1 video + 1 audio stream, duration within 0.1 s, A/V within 50 ms. The caption band diff still passes.
- **Cache:** the render key changes when the track changes.
- **Real check:** run `--again` on the owner's podcast, then look at a contact sheet of before/after frames from several clips.

## 5. Risks

| Risk | Mitigation |
|---|---|
| A profile or a cap brim hides the face | Score threshold 0.6, and the median over 3 samples; if nothing is found, blur instead of a wrong crop |
| Fast motion or a flash reads as a cut | The threshold is tuned on the podcast, and shots under 0.5 s are merged |
| The person leans out of the fixed crop within a shot | Accepted; smoothed tracking stays in the roadmap |
| Low-resolution sources (640x360) | Framing is right but soft; the owner uses 1080p originals where possible |
| OpenCV 5 API changes | `FaceDetectorYN` is pinned through `uv.lock`, and a fast test exercises the real detector |

## 6. Out of scope

- Active-speaker selection (diarization or mouth motion).
- Smoothed in-shot tracking.
- Vertical re-composition of two people (split screen).
- Using face detection for thumbnails.
