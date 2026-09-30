"""YuNet face detection on real faces (the talking-head fixture pasted into two_shot)."""

from pathlib import Path

import pytest

from clipforge.config import Settings
from clipforge.stages.faces import YUNET_MODEL, YuNetDetector, sample_frame, sample_size
from tests.conftest import requires_ffmpeg

pytestmark = requires_ffmpeg
MODEL = Settings(_env_file=None).models_dir / YUNET_MODEL


def test_sample_size_keeps_the_aspect_and_even_height() -> None:
    assert sample_size(1280, 720) == (640, 360)
    assert sample_size(1921, 1081) == (640, 360)
    assert sample_size(640, 360) == (640, 360)


def test_sample_frame_decodes_bgr(two_shot: Path) -> None:
    frame = sample_frame(two_shot, 0.5, (640, 360))
    assert frame is not None and frame.shape == (360, 640, 3)


def test_sample_frame_of_a_bad_file_is_none(tmp_path: Path) -> None:
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"nope")
    assert sample_frame(bad, 0.5, (640, 360)) is None


@pytest.mark.parametrize(("t", "lo", "hi"), [(0.5, 20, 200), (2.5, 450, 620)])
def test_yunet_finds_the_face(two_shot: Path, t: float, lo: float, hi: float) -> None:
    frame = sample_frame(two_shot, t, (640, 360))
    assert frame is not None
    faces = YuNetDetector(MODEL).detect(frame)
    assert len(faces) == 1
    assert lo < faces[0].cx < hi and faces[0].score >= 0.6  # left shot, then right shot


def test_yunet_finds_nothing_in_a_test_pattern(tmp_path: Path, media) -> None:  # type: ignore[no-untyped-def]
    frame = sample_frame(media(width=1280, height=720, duration_s=2.0), 1.0, (640, 360))
    assert frame is not None
    assert YuNetDetector(MODEL).detect(frame) == []


def test_missing_model_fails_on_first_use_not_at_construction(two_shot: Path) -> None:
    detector = YuNetDetector(Path("/nonexistent/model.onnx"))  # must not raise here
    frame = sample_frame(two_shot, 0.5, (640, 360))
    assert frame is not None
    with pytest.raises(Exception):  # noqa: B017 (cv2.error or FileNotFoundError)
        detector.detect(frame)


def test_yunet_returns_mouth_corners_inside_the_face(two_shot: Path) -> None:
    frame = sample_frame(two_shot, 0.5, (640, 360))
    assert frame is not None
    (face,) = YuNetDetector(MODEL).detect(frame)
    assert face.mouth_left is not None and face.mouth_right is not None
    for x, y in (face.mouth_left, face.mouth_right):
        assert face.cx - face.w / 2 <= x <= face.cx + face.w / 2
        assert face.cy <= y <= face.cy + face.h / 2  # below the center, inside the box
