import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest

from clipforge.config import Settings
from clipforge.models import ClipOptions, ClipSpec, CropBox, Word
from clipforge.stages import reframe as reframe_module
from clipforge.stages import speakers
from clipforge.stages.faces import YUNET_MODEL, Face, YuNetDetector
from clipforge.stages.reframe import crop_box, plan, track
from clipforge.stages.speakers import Motion
from tests.conftest import TWO_SHOT_FACE_X, requires_ffmpeg
from tests.stages.helpers import make_ctx, source_from, spec_for
from tests.test_models import make_source, make_spec


def spec(width: int, height: int, mode: str = "auto") -> ClipSpec:
    source = make_source().model_copy(update={"width": width, "height": height})
    return make_spec().model_copy(update={"source": source, "options": ClipOptions(reframe=mode)})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("width", "height", "mode", "expected"),
    [
        (1920, 1080, "auto", CropBox(x=656, y=0, w=608, h=1080)),  # 16:9: center crop
        (1440, 1080, "auto", CropBox(x=416, y=0, w=608, h=1080)),  # 4:3 is still landscape
        (1280, 720, "center", CropBox(x=438, y=0, w=404, h=720)),
        (1921, 1081, "auto", CropBox(x=656, y=0, w=608, h=1080)),  # odd sizes give even crops
        (1080, 1080, "center", CropBox(x=236, y=0, w=608, h=1080)),  # forced center on square
        (720, 1600, "center", CropBox(x=0, y=160, w=720, h=1280)),  # taller than 9:16
        (1080, 1920, "auto", CropBox(x=0, y=0, w=1080, h=1920)),  # already 9:16: full frame
        (1080, 1920, "blur", CropBox(x=0, y=0, w=1080, h=1920)),  # nothing to blur
    ],
)
def test_center_crops(width: int, height: int, mode: str, expected: CropBox) -> None:
    track = plan(spec(width, height, mode))
    assert track.mode == "center" and track.box == expected
    assert (track.out_width, track.out_height) == (1080, 1920)


@pytest.mark.parametrize(
    ("width", "height", "mode"),
    [(1080, 1080, "auto"), (720, 1600, "auto"), (1920, 1080, "blur"), (1080, 1350, "auto")],
)
def test_blur_fallback(width: int, height: int, mode: str) -> None:
    track = plan(spec(width, height, mode))
    assert track.mode == "blur_fallback" and track.box is None


# ---- per-shot face tracking (ADR-19)


SETTINGS = Settings(_env_file=None)


@dataclass
class FakeDetector:
    faces: list[Face] = field(default_factory=list)
    fail: bool = False
    calls: int = 0
    name: str = "fake"

    def detect(self, frame: npt.NDArray[np.uint8]) -> list[Face]:
        self.calls += 1
        if self.fail:
            raise RuntimeError("cv2 exploded")
        return list(self.faces)


def test_crop_box_is_clamped() -> None:
    assert crop_box(640, 1280, 720) == CropBox(x=438, y=0, w=404, h=720)
    assert crop_box(0, 1280, 720).x == 0
    right = crop_box(1280, 1280, 720)
    assert right.x + right.w <= 1280 and right.x == 876
    odd = crop_box(700, 1921, 1081)
    assert odd.w % 2 == 0 and odd.h % 2 == 0 and odd.x % 2 == 0


@requires_ffmpeg
def test_two_shots_each_framed_on_its_face(tmp_path: Path, two_shot: Path) -> None:
    spec = spec_for(source_from(tmp_path, two_shot), "auto", start=0.0, end=4.0)
    detector = YuNetDetector(SETTINGS.models_dir / YUNET_MODEL)
    result = track(make_ctx(tmp_path), spec, [], detector, SETTINGS)
    assert result.mode == "tracked" and len(result.segments) == 2
    assert abs(result.segments[0].end - 2.0) < 0.05 and result.segments[-1].end == 4.0
    for segment, left in zip(result.segments, TWO_SHOT_FACE_X, strict=True):
        assert segment.mode == "crop" and segment.box is not None
        box = segment.box
        assert box.x <= left and left + 338 <= box.x + box.w  # the whole person is in frame
        assert box.x >= 0 and box.x + box.w <= 1280


@requires_ffmpeg
def test_shot_without_faces_blurs(tmp_path: Path, media) -> None:  # type: ignore[no-untyped-def]
    source = source_from(tmp_path, media(width=1280, height=720, duration_s=4.0))
    result = track(make_ctx(tmp_path), spec_for(source, "auto"), [], FakeDetector(), SETTINGS)
    assert [s.mode for s in result.segments] == ["blur"]


@requires_ffmpeg
def test_largest_face_wins(tmp_path: Path, media) -> None:  # type: ignore[no-untyped-def]
    source = source_from(tmp_path, media(width=1280, height=720, duration_s=4.0))
    small = Face(cx=100, cy=100, w=40, h=50, score=0.9)
    big = Face(cx=500, cy=180, w=120, h=150, score=0.8)
    detector = FakeDetector(faces=[small, big])
    result = track(make_ctx(tmp_path), spec_for(source, "auto"), [], detector, SETTINGS)
    box = result.segments[0].box
    assert box is not None and box.x <= 1000 <= box.x + box.w  # 500 px at 640 = 1000 at 1280


@requires_ffmpeg
def test_tiny_faces_are_ignored(tmp_path: Path, media) -> None:  # type: ignore[no-untyped-def]
    source = source_from(tmp_path, media(width=1280, height=720, duration_s=4.0))
    poster = Face(cx=600, cy=40, w=20, h=24, score=0.95)  # 20/640 = 3% of the width
    result = track(
        make_ctx(tmp_path), spec_for(source, "auto"), [], FakeDetector([poster]), SETTINGS
    )
    assert [s.mode for s in result.segments] == ["blur"]


@requires_ffmpeg
def test_detector_failure_blurs_the_whole_clip(
    tmp_path: Path, two_shot: Path, caplog: pytest.LogCaptureFixture
) -> None:
    spec = spec_for(source_from(tmp_path, two_shot), "auto", start=0.0, end=4.0)
    with caplog.at_level(logging.WARNING):
        result = track(make_ctx(tmp_path), spec, [], FakeDetector(fail=True), SETTINGS)
    assert [(s.start, s.end, s.mode) for s in result.segments] == [(0.0, 4.0, "blur")]
    assert "face reframing failed" in caplog.text


@pytest.mark.parametrize(
    ("width", "height", "mode", "expected"),
    [
        (1080, 1920, "auto", "center"),  # already 9:16
        (1080, 1080, "auto", "blur_fallback"),  # near-square: blur-fit, as before
        (1920, 1080, "center", "center"),
        (1920, 1080, "blur", "blur_fallback"),
    ],
)
def test_track_delegates_to_plan_without_detecting(
    tmp_path: Path, width: int, height: int, mode: str, expected: str
) -> None:
    detector = FakeDetector()
    result = track(make_ctx(tmp_path), spec(width, height, mode), [], detector, SETTINGS)
    assert result.mode == expected and detector.calls == 0


@requires_ffmpeg
def test_track_is_cached_and_rebound(tmp_path: Path, two_shot: Path) -> None:
    source = source_from(tmp_path, two_shot)
    first = spec_for(source, "auto", start=0.0, end=4.0)
    detector = FakeDetector(faces=[Face(cx=300, cy=150, w=100, h=120, score=0.9)])
    track(make_ctx(tmp_path), first, [], detector, SETTINGS)
    calls = detector.calls
    again = first.model_copy(update={"clip_id": "clip_07", "rank": 7})
    result = track(make_ctx(tmp_path), again, [], detector, SETTINGS)
    assert detector.calls == calls and result.clip_id == "clip_07"


@requires_ffmpeg
def test_detection_failure_is_not_cached(tmp_path: Path, two_shot: Path) -> None:
    spec = spec_for(source_from(tmp_path, two_shot), "auto", start=0.0, end=4.0)
    track(make_ctx(tmp_path), spec, [], FakeDetector(fail=True), SETTINGS)  # blurred, not stored
    face = Face(cx=300, cy=150, w=100, h=120, score=0.9)
    again = track(make_ctx(tmp_path), spec, [], FakeDetector(faces=[face]), SETTINGS)
    assert all(s.mode == "crop" for s in again.segments)


@requires_ffmpeg
def test_undecodable_samples_are_not_cached(
    tmp_path: Path, two_shot: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from clipforge.stages import faces as faces_module

    spec = spec_for(source_from(tmp_path, two_shot), "auto", start=0.0, end=4.0)
    real = faces_module.sample_frame
    monkeypatch.setattr(faces_module, "sample_frame", lambda *a, **k: None)
    face = Face(cx=300, cy=150, w=100, h=120, score=0.9)
    first = track(make_ctx(tmp_path), spec, [], FakeDetector(faces=[face]), SETTINGS)
    assert all(s.mode == "blur" for s in first.segments)
    monkeypatch.setattr(faces_module, "sample_frame", real)
    again = track(make_ctx(tmp_path), spec, [], FakeDetector(faces=[face]), SETTINGS)
    assert all(s.mode == "crop" for s in again.segments)


@dataclass
class SequenceDetector:
    """Returns one scripted answer per call (per sample)."""

    answers: list[list[Face]]
    name: str = "sequence"

    def detect(self, frame: npt.NDArray[np.uint8]) -> list[Face]:
        return self.answers.pop(0) if self.answers else []


@requires_ffmpeg
def test_two_samples_never_average_two_people(tmp_path: Path, media) -> None:  # type: ignore[no-untyped-def]
    source = source_from(tmp_path, media(width=1280, height=720, duration_s=4.0))
    left = Face(cx=100, cy=180, w=60, h=70, score=0.9)  # smaller
    right = Face(cx=500, cy=180, w=120, h=140, score=0.9)  # larger
    detector = SequenceDetector([[left], [right], []])  # faces in 2 of 3 samples
    result = track(make_ctx(tmp_path), spec_for(source, "auto"), [], detector, SETTINGS)
    box = result.segments[0].box
    assert box is not None and box.x <= 1000 <= box.x + box.w  # the larger face (500 at 640)


# ---- speaker-aware framing (ADR-21)

NO_CUTS = Settings(_env_file=None, scene_threshold=0.99)  # one shot, whatever testsrc2 does

LEFT_FACE = Face(cx=100, cy=180, w=60, h=70, score=0.9)  # 1280x720 source, sample 640x360
RIGHT_FACE = Face(cx=540, cy=180, w=60, h=70, score=0.9)


def words_at(*spans: tuple[float, float]) -> list[Word]:
    return [Word(text="w", start=s, end=e) for s, e in spans]


def scripted_motion(switch: float) -> Callable[..., Motion]:
    """A mouth_motion stand-in: the left seat talks before `switch` (clip seconds), the right
    after. `start` is the shot start in source seconds; returned times are relative to it."""

    def fake(
        video: Path, start: float, end: float, seat_list: object, size: object, fps: int = 10
    ) -> Motion:
        times = np.arange(0.05, end - start, 0.1)
        clip_t = times + (start - 1.0)  # spec_for's clip starts at 1.0 s of the source
        left = np.where(clip_t < switch, 5.0, 0.5)
        return Motion(times=times, scores=np.column_stack([left, 5.5 - left]))

    return fake


@requires_ffmpeg
def test_two_seats_cut_to_whoever_talks(
    tmp_path: Path,
    media,  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = source_from(tmp_path, media(width=1280, height=720, duration_s=6.0))
    spec = spec_for(source, "auto", start=1.0, end=6.0)  # one 5 s shot
    monkeypatch.setattr(speakers, "mouth_motion", scripted_motion(switch=2.5))
    words = words_at((0.2, 1.0), (1.1, 2.3), (2.7, 3.5), (3.6, 4.8))
    detector = FakeDetector(faces=[LEFT_FACE, RIGHT_FACE])
    result = track(make_ctx(tmp_path), spec, words, detector, NO_CUTS)
    assert [(s.start, s.end) for s in result.segments] == [(0.0, 2.5), (2.5, 5.0)]
    left_box, right_box = (s.box for s in result.segments)
    assert left_box is not None and left_box.x <= 200 <= left_box.x + left_box.w
    assert right_box is not None and right_box.x <= 1080 <= right_box.x + right_box.w


@requires_ffmpeg
def test_close_seats_share_one_centered_crop(tmp_path: Path, media) -> None:  # type: ignore[no-untyped-def]
    source = source_from(tmp_path, media(width=1280, height=720, duration_s=4.0))
    a = Face(cx=290, cy=180, w=50, h=60, score=0.9)
    b = Face(cx=350, cy=180, w=50, h=60, score=0.9)  # span 265..375 = 110 px, crop is 202
    result = track(make_ctx(tmp_path), spec_for(source, "auto"), [], FakeDetector([a, b]), NO_CUTS)
    (segment,) = result.segments
    assert segment.box is not None
    assert abs(segment.box.x + segment.box.w / 2 - 640) <= 2  # centered on 320 at 640 = 640


@requires_ffmpeg
def test_two_seats_without_words_use_largest_face_and_cache(tmp_path: Path, media) -> None:  # type: ignore[no-untyped-def]
    source = source_from(tmp_path, media(width=1280, height=720, duration_s=4.0))
    big = Face(cx=540, cy=180, w=90, h=100, score=0.9)
    detector = FakeDetector(faces=[LEFT_FACE, big])
    spec = spec_for(source, "auto")
    first = track(make_ctx(tmp_path), spec, [], detector, NO_CUTS)
    box = first.segments[0].box
    assert box is not None and box.x <= 1080 <= box.x + box.w  # the larger face
    calls = detector.calls
    track(make_ctx(tmp_path), spec, [], detector, NO_CUTS)
    assert detector.calls == calls  # cached: not a degraded result


@requires_ffmpeg
def test_motion_failure_falls_back_and_is_not_cached(
    tmp_path: Path,
    media,  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = source_from(tmp_path, media(width=1280, height=720, duration_s=6.0))
    spec = spec_for(source, "auto", start=1.0, end=6.0)
    words = words_at((0.2, 2.3), (2.7, 4.8))
    detector = FakeDetector(faces=[LEFT_FACE, RIGHT_FACE])

    def broken(*args: object, **kwargs: object) -> Motion:
        raise RuntimeError("ffmpeg died")

    monkeypatch.setattr(speakers, "mouth_motion", broken)
    first = track(make_ctx(tmp_path), spec, words, detector, NO_CUTS)
    assert len(first.segments) == 1 and first.segments[0].mode == "crop"  # largest face
    monkeypatch.setattr(speakers, "mouth_motion", scripted_motion(switch=2.5))
    again = track(make_ctx(tmp_path), spec, words, detector, NO_CUTS)
    assert len(again.segments) == 2  # recomputed, not served from the cache


@requires_ffmpeg
def test_cache_key_changes_with_word_timings(
    tmp_path: Path,
    media,  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = source_from(tmp_path, media(width=1280, height=720, duration_s=6.0))
    spec = spec_for(source, "auto", start=1.0, end=6.0)
    monkeypatch.setattr(speakers, "mouth_motion", scripted_motion(switch=2.5))
    detector = FakeDetector(faces=[LEFT_FACE, RIGHT_FACE])
    track(make_ctx(tmp_path), spec, words_at((0.2, 2.3), (2.7, 4.8)), detector, NO_CUTS)
    calls = detector.calls
    track(make_ctx(tmp_path), spec, words_at((0.2, 2.0), (2.7, 4.8)), detector, NO_CUTS)
    assert detector.calls > calls


def test_stage_version_is_4() -> None:
    assert reframe_module.STAGE_VERSION == "4"
