"""Two-pass loudness helpers (proposed ADR-47, log #341)."""

import json
import re
from pathlib import Path

import pytest

from clipforge import ffmpeg
from clipforge.stages import loudness
from tests.conftest import requires_ffmpeg

PASS1 = """[Parsed_loudnorm_0 @ 0x1]
{
\t"input_i" : "-16.23",
\t"input_tp" : "-1.30",
\t"input_lra" : "3.40",
\t"input_thresh" : "-26.51",
\t"output_i" : "-14.50",
\t"output_tp" : "-1.00",
\t"output_lra" : "3.30",
\t"output_thresh" : "-24.70",
\t"normalization_type" : "dynamic",
\t"target_offset" : "0.12"
}
"""


def test_single_pass_is_todays_filter() -> None:
    assert loudness.single_pass(-14.0) == "loudnorm=I=-14:TP=-1.5:LRA=11"


def test_parse_reads_the_last_measurement() -> None:
    m = loudness.parse("noise\n" + PASS1)
    assert m == loudness.Measured(i=-16.23, tp=-1.3, lra=3.4, thresh=-26.51, offset=0.12)


def test_parse_returns_none_for_silence() -> None:
    assert loudness.parse(PASS1.replace('"-16.23"', '"-inf"')) is None


def test_parse_raises_without_a_measurement() -> None:
    with pytest.raises(ValueError):
        loudness.parse("ffmpeg said nothing useful")


def test_second_pass_carries_the_measurement() -> None:
    m = loudness.Measured(i=-16.23, tp=-1.3, lra=3.4, thresh=-26.51, offset=0.12)
    assert loudness.second_pass(m, -14.0) == (
        "loudnorm=I=-14:TP=-1.5:LRA=11:measured_I=-16.23:measured_TP=-1.30:"
        "measured_LRA=3.40:measured_thresh=-26.51:offset=0.12:linear=true"
    )


@pytest.mark.parametrize(
    ("tp", "lra", "expected"),
    [(-1.3, 3.4, "dynamic"), (-23.9, 0.7, "linear"), (-20.0, 12.0, "dynamic")],
)
def test_mode_follows_ffmpegs_rule(tp: float, lra: float, expected: str) -> None:
    m = loudness.Measured(i=-30.0 if tp < -10 else -16.2, tp=tp, lra=lra, thresh=-40.0, offset=0)
    assert loudness.mode(m, -14.0) == expected


WOBBLE = "volume='if(lt(mod(t,2),1),1,0.3)':eval=frame"  # gives LRA > 0


@requires_ffmpeg
@pytest.mark.parametrize(
    ("shape", "expected"),
    [
        (f"{WOBBLE},volume=-10dB", "linear"),  # measured 2026-10-01: I -34.8, TP -27.8, LRA 2.5
        (f"{WOBBLE},volume='if(lt(t,5.9),0.05,8)':eval=frame", "dynamic"),  # LRA 20 > 11
        ("volume=-20dB", "dynamic"),  # a steady tone: LRA 0, which ffmpeg never runs linear
    ],
)
def test_mode_agrees_with_ffmpeg(tmp_path: Path, shape: str, expected: str) -> None:
    wav = tmp_path / "tone.wav"
    ffmpeg.run(["-f", "lavfi", "-i", f"sine=f=440:d=6:sample_rate=48000,{shape}", str(wav)])
    first = ffmpeg.run(
        ["-i", str(wav), "-af", loudness.measure_filter(-14.0), "-f", "null", "-"],
        loglevel="info",
    )
    m = loudness.parse(first)
    assert m is not None
    second = ffmpeg.run(
        ["-i", str(wav), "-af", loudness.second_pass(m, -14.0) + ":print_format=json",
         "-f", "null", "-"],
        loglevel="info",
    )  # fmt: skip
    reported = json.loads(re.findall(r"\{[^{}]*\}", second)[-1])["normalization_type"]
    assert loudness.mode(m, -14.0) == reported == expected
