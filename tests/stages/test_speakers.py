"""Speaker-aware framing helpers (ADR-21)."""

from __future__ import annotations

import itertools
import subprocess
from pathlib import Path

import numpy as np
import pytest

from clipforge.models import Word
from clipforge.stages.faces import Face
from clipforge.stages.speakers import (
    MOTION_FPS,
    Motion,
    Seat,
    Turn,
    assign_words,
    eye_band,
    fits_one_crop,
    group_center,
    mouth_motion,
    mouth_patch,
    seats,
    turns,
)
from tests.conftest import requires_ffmpeg


def face(cx: float, w: float = 60, cy: float = 150, h: float = 80) -> Face:
    return Face(cx=cx, cy=cy, w=w, h=h, score=0.9)


def test_seats_group_by_position_and_sort_left_to_right() -> None:
    samples = [[face(480), face(150)], [face(152), face(478)], [face(149), face(481)]]
    found = seats(samples)
    assert [round(s.cx) for s in found] == [150, 480]


def test_a_face_seen_once_is_not_a_seat() -> None:
    samples = [[face(150), face(480)], [face(150)], [face(151)]]
    assert [round(s.cx) for s in seats(samples)] == [150]


def test_two_faces_in_one_sample_are_two_seats_even_if_close() -> None:
    samples = [[face(150, w=60), face(215, w=60)]] * 3  # 65 px apart, wider than 60
    assert len(seats(samples)) == 2


def test_seat_is_the_median_detection() -> None:
    samples = [[face(100)], [face(110)], [face(200 - 70)]]  # 100, 110, 130
    (seat,) = seats(samples)
    assert seat.cx == 110


def test_fits_one_crop() -> None:
    close = [Seat(face(150)), Seat(face(230))]  # span 120..260 = 140, padded 154
    far = [Seat(face(150)), Seat(face(480))]  # span 120..510 = 390
    assert fits_one_crop(close, crop_w=202)
    assert not fits_one_crop(far, crop_w=202)
    assert group_center(close) == 190


def test_mouth_patch_uses_the_landmarks() -> None:
    f = Face(cx=100, cy=100, w=60, h=80, score=0.9, mouth_left=(90, 120), mouth_right=(110, 122))
    assert mouth_patch(f) == (81, 113, 119, 133)  # 90-9, 121-8, 110+9, 121+12


def test_mouth_patch_estimated_without_landmarks() -> None:
    f = face(100, w=60, cy=100, h=80)  # corners estimated at (88, 120) and (112, 120)
    assert mouth_patch(f) == (79, 112, 121, 132)


def test_eye_band_is_the_top_45_percent() -> None:
    assert eye_band(face(100, w=60, cy=100, h=80)) == (70, 60, 130, 96)


@pytest.mark.parametrize("samples", [[], [[], [], []]])
def test_no_faces_no_seats(samples: list[list[Face]]) -> None:
    assert seats(samples) == []


LEFT, RIGHT = face(160, w=80, cy=150, h=100), face(480, w=80, cy=150, h=100)


def talking_pair(path: Path) -> Path:
    """640x360, 4 s, gray: noise flickers in LEFT's mouth patch for 0-2 s and in RIGHT's for
    2-4 s. Nothing moves in either eye band."""
    (lx0, ly0, lx1, ly1), (rx0, ry0, rx1, ry1) = mouth_patch(LEFT), mouth_patch(RIGHT)
    noise = "color=c=gray:s=640x360:r=25:d=4,noise=alls=100:allf=t"
    graph = (
        f"[1:v]crop={lx1 - lx0}:{ly1 - ly0}:0:0[n1];[2:v]crop={rx1 - rx0}:{ry1 - ry0}:0:0[n2];"
        f"[0:v][n1]overlay=x={lx0}:y={ly0}:enable='lt(t,2)'[a];"
        f"[a][n2]overlay=x={rx0}:y={ry0}:enable='gte(t,2)'[v]"
    )
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=0x606060:s=640x360:r=25:d=4",
        "-f", "lavfi", "-i", noise, "-f", "lavfi", "-i", noise,
        "-filter_complex", graph, "-map", "[v]",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "12", "-pix_fmt", "yuv420p",
        str(path),
    ]  # fmt: skip
    subprocess.run(cmd, check=True, capture_output=True)
    return path


@requires_ffmpeg
def test_mouth_motion_follows_the_talking_seat(tmp_path: Path) -> None:
    video = talking_pair(tmp_path / "pair.mp4")
    motion = mouth_motion(video, 0.0, 4.0, [Seat(LEFT), Seat(RIGHT)], (640, 360))
    assert motion.scores.shape == (len(motion.times), 2)
    assert 35 <= len(motion.times) <= 40  # 10 fps over 4 s, minus one per pair
    first = motion.times < 1.9
    second = motion.times > 2.1
    assert motion.scores[first, 0].mean() > 3 * motion.scores[first, 1].mean()
    assert motion.scores[second, 1].mean() > 3 * motion.scores[second, 0].mean()


@requires_ffmpeg
def test_mouth_motion_times_are_relative_to_start(tmp_path: Path) -> None:
    video = talking_pair(tmp_path / "pair.mp4")
    motion = mouth_motion(video, 1.0, 3.0, [Seat(LEFT), Seat(RIGHT)], (640, 360))
    assert motion.times[0] == pytest.approx(0.5 / MOTION_FPS)
    assert motion.times[-1] < 2.0


@requires_ffmpeg
def test_mouth_motion_of_a_bad_file_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"nope")
    with pytest.raises(RuntimeError):
        mouth_motion(bad, 0.0, 2.0, [Seat(LEFT)], (640, 360))


@requires_ffmpeg
def test_patch_off_the_frame_scores_zero(tmp_path: Path) -> None:
    video = talking_pair(tmp_path / "pair.mp4")
    off = Seat(face(-200, w=80))  # entirely left of the frame
    motion = mouth_motion(video, 0.0, 2.0, [off, Seat(LEFT)], (640, 360))
    assert (motion.scores[:, 0] == 0).all() and motion.scores[:, 1].mean() > 0


def motion(rows: list[tuple[float, float, float]]) -> Motion:
    """(time, left score, right score) rows."""
    arr = np.array(rows, dtype=np.float64)
    return Motion(times=arr[:, 0], scores=arr[:, 1:])


def word(start: float, end: float) -> Word:
    return Word(text="w", start=start, end=end)


def test_assign_words_picks_the_seat_that_moved_most() -> None:
    m = motion([(0.05, 5, 1), (0.15, 6, 1), (0.25, 1, 7), (0.35, 1, 8)])
    assert assign_words([word(0.0, 0.2), word(0.2, 0.4)], m) == [0, 1]


def test_near_tie_is_unknown() -> None:
    m = motion([(0.05, 5.0, 4.5), (0.15, 5.0, 4.5)])  # 5 < 1.2 * 4.5
    assert assign_words([word(0.0, 0.2)], m) == [None]


def test_no_motion_is_unknown() -> None:
    assert assign_words([word(0.0, 0.2)], motion([(0.05, 0, 0), (0.15, 0, 0)])) == [None]


def test_word_without_frames_is_unknown() -> None:
    assert assign_words([word(5.0, 5.2)], motion([(0.05, 5, 1)])) == [None]


def test_zero_length_word_uses_nearby_frames() -> None:
    m = motion([(0.97, 1, 9), (1.03, 1, 9)])
    assert assign_words([word(1.0, 1.0)], m) == [1]


def test_motion_shifted() -> None:
    m = motion([(0.05, 1, 2)]).shifted(2.0)
    assert m.times.tolist() == [2.05] and m.scores.tolist() == [[1, 2]]


def said(*spans: tuple[float, float, int | None]) -> tuple[list[Word], list[int | None]]:
    """Words given as (start, end, seat)."""
    return [word(s, e) for s, e, _ in spans], [seat for _, _, seat in spans]


def covers(result: list[Turn], start: float, end: float) -> None:
    assert result[0].start == start and result[-1].end == end
    for a, b in itertools.pairwise(result):
        assert a.end == b.start and a.seat != b.seat and a.end > a.start


def test_alternating_turns_switch_mid_pause() -> None:
    words, ids = said((0.5, 1.5, 0), (1.6, 3.2, 0), (3.6, 5.0, 1), (5.1, 6.8, 1), (7.2, 9.5, 0))
    result = turns(words, ids, 0.0, 10.0)
    assert result == [Turn(0.0, 3.4, 0), Turn(3.4, 7.0, 1), Turn(7.0, 10.0, 0)]
    covers(result, 0.0, 10.0)


def test_short_interjection_merges_into_the_longer_neighbor() -> None:
    words, ids = said((0.0, 3.0, 0), (3.2, 3.8, 1), (4.0, 9.0, 0))  # a 0.6 s "yeah"
    assert turns(words, ids, 0.0, 9.0) == [Turn(0.0, 9.0, 0)]


def test_short_interruption_leaves_one_turn() -> None:
    words, ids = said((0.0, 2.5, 0), (2.6, 3.0, 1), (3.1, 6.0, 0), (6.4, 9.0, 1))
    result = turns(words, ids, 0.0, 9.0)
    assert result == [Turn(0.0, 6.2, 0), Turn(6.2, 9.0, 1)]
    covers(result, 0.0, 9.0)


def test_initial_silence_goes_to_the_first_speaker() -> None:
    words, ids = said((3.0, 6.0, 1), (6.4, 9.0, 0))
    assert turns(words, ids, 0.0, 10.0) == [Turn(0.0, 6.2, 1), Turn(6.2, 10.0, 0)]


def test_unknown_words_join_the_turn_before_them() -> None:
    words, ids = said((0.0, 1.0, None), (1.1, 2.5, 0), (2.6, 3.0, None), (3.5, 6.0, 1))
    assert turns(words, ids, 0.0, 6.0) == [Turn(0.0, 3.25, 0), Turn(3.25, 6.0, 1)]


def test_all_unknown_is_none() -> None:
    words, ids = said((0.0, 1.0, None), (1.2, 2.0, None))
    assert turns(words, ids, 0.0, 3.0) is None
    assert turns([], [], 0.0, 3.0) is None


def test_one_speaker_is_one_turn() -> None:
    words, ids = said((0.2, 1.0, 1), (1.2, 1.8, 1))
    assert turns(words, ids, 0.0, 1.9) == [Turn(0.0, 1.9, 1)]


def test_turns_clamp_words_to_the_shot() -> None:
    words, ids = said((1.9, 2.1, 0), (2.2, 4.4, 0), (4.6, 7.0, 1), (7.8, 8.3, 1))
    result = turns(words, ids, 2.0, 8.0)  # the shot is [2, 8): first and last words overlap it
    assert result == [Turn(2.0, 4.5, 0), Turn(4.5, 8.0, 1)]
    covers(result, 2.0, 8.0)


def test_boundaries_are_milliseconds() -> None:
    words, ids = said((0.0, 2.5, 0), (2.6001, 5.0, 1))
    (_, second) = turns(words, ids, 0.0, 5.0) or []
    assert second.start == 2.55


def test_overlapping_words_still_give_contiguous_turns() -> None:
    # a long word overlapping the next runs puts the switch points out of order (review)
    words, ids = said((0.0, 9.0, 0), (2.0, 4.5, 1), (5.0, 7.5, 2))
    result = turns(words, ids, 0.0, 10.0)
    assert result is not None
    covers(result, 0.0, 10.0)
