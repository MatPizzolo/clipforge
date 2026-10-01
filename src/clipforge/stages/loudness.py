"""Two-pass loudness normalization (ADR-20 targets; ADR-47, log #341).

Pass 1 measures the audio graph with loudnorm's JSON report; pass 2 applies the measured
values with linear=true. ffmpeg itself uses linear gain only when that keeps the true peak
under TP and the measured LRA within the target, otherwise dynamic (`mode`)."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Literal

TP = -1.5
LRA = 11.0
SILENCE_LUFS = -70.0  # loudnorm's own floor
_JSON = re.compile(r"\{[^{}]*\"input_i\"[^{}]*\}")


@dataclass(frozen=True)
class Measured:
    i: float
    tp: float
    lra: float
    thresh: float
    offset: float


def single_pass(target: float) -> str:
    return f"loudnorm=I={target:g}:TP={TP:g}:LRA={LRA:g}"


def measure_filter(target: float) -> str:
    return single_pass(target) + ":print_format=json"


def parse(stderr: str) -> Measured | None:
    """Pass 1's measurement; None for silence. ValueError when there is none to read."""
    blocks = _JSON.findall(stderr)
    if not blocks:
        raise ValueError("no loudnorm measurement in ffmpeg's output")
    data = json.loads(blocks[-1])
    i = float(data["input_i"])
    if not math.isfinite(i) or i <= SILENCE_LUFS:
        return None
    m = Measured(
        i=i,
        tp=float(data["input_tp"]),
        lra=float(data["input_lra"]),
        thresh=float(data["input_thresh"]),
        offset=float(data["target_offset"]),
    )
    if not all(math.isfinite(v) for v in (m.tp, m.lra, m.thresh, m.offset)):
        raise ValueError("loudnorm measurement is not finite")
    return m


def second_pass(m: Measured, target: float) -> str:
    return (
        f"{single_pass(target)}:measured_I={m.i:.2f}:measured_TP={m.tp:.2f}"
        f":measured_LRA={m.lra:.2f}:measured_thresh={m.thresh:.2f}:offset={m.offset:.2f}"
        ":linear=true"
    )


def mode(m: Measured, target: float) -> Literal["linear", "dynamic"]:
    """ffmpeg's rule (libavfilter/af_loudnorm.c, init): linear only when the gain keeps
    the true peak under TP and the measured LRA is within the target LRA."""
    usable = m.tp != 99 and m.thresh != -70 and m.lra != 0 and m.i != 0
    peak_after = m.tp + (target - m.i)
    return "linear" if usable and peak_after <= TP and m.lra <= LRA else "dynamic"
