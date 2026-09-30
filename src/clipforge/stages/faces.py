"""Face detection for reframing (ADR-19): OpenCV's YuNet on a few small frames per shot.

cv2 is imported on first use, so importing this module is cheap and a broken OpenCV install
surfaces as a detection failure (reframe falls back to blur) instead of an import error."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import numpy.typing as npt

YUNET_MODEL = "face_detection_yunet_2023mar.onnx"
SAMPLE_WIDTH = 640


@dataclass(frozen=True)
class Face:
    cx: float  # center, in pixels of the frame given to detect()
    cy: float
    w: float
    h: float
    score: float
    mouth_left: tuple[float, float] | None = None  # YuNet landmarks; None from box-only detectors
    mouth_right: tuple[float, float] | None = None

    @property
    def area(self) -> float:
        return self.w * self.h


class FaceDetector(Protocol):
    name: str  # part of the reframe cache key

    def detect(self, frame: npt.NDArray[np.uint8]) -> list[Face]: ...


class YuNetDetector:
    def __init__(self, model_path: Path, score_threshold: float = 0.6) -> None:
        self.model_path = model_path
        self.score_threshold = score_threshold
        self.name = f"yunet:{model_path.name}:{score_threshold:g}"
        self._net: Any = None

    def _load(self) -> Any:
        if self._net is None:
            import cv2

            if not self.model_path.is_file():
                raise FileNotFoundError(f"face model not found: {self.model_path}")
            self._net = cv2.FaceDetectorYN.create(
                str(self.model_path), "", (SAMPLE_WIDTH, 360), self.score_threshold
            )
        return self._net

    def detect(self, frame: npt.NDArray[np.uint8]) -> list[Face]:
        net = self._load()
        height, width = frame.shape[:2]
        net.setInputSize((width, height))
        _, found = net.detect(frame)
        if found is None:
            return []
        return [
            Face(
                cx=float(f[0] + f[2] / 2),
                cy=float(f[1] + f[3] / 2),
                w=float(f[2]),
                h=float(f[3]),
                score=float(f[14]),
                mouth_left=_mouth(f)[0],
                mouth_right=_mouth(f)[1],
            )
            for f in found
        ]


def _mouth(row: Any) -> tuple[tuple[float, float], tuple[float, float]]:
    """YuNet's two mouth corners (columns 10-13), ordered left to right in the image."""
    a = (float(row[10]), float(row[11]))
    b = (float(row[12]), float(row[13]))
    return (a, b) if a[0] <= b[0] else (b, a)


def sample_size(width: int, height: int) -> tuple[int, int]:
    """640 px wide, even height, same aspect as the (display-oriented) source."""
    h = round(SAMPLE_WIDTH * height / width)
    return SAMPLE_WIDTH, h - h % 2


def sample_frame(video: Path, t: float, size: tuple[int, int]) -> npt.NDArray[np.uint8] | None:
    """One BGR frame at `t` seconds of the source, scaled to `size`; None if undecodable."""
    w, h = size
    cmd = [
        "ffmpeg", "-v", "error", "-nostdin", "-ss", f"{max(t, 0.0):.3f}", "-i", str(video),
        "-frames:v", "1", "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-",
    ]  # fmt: skip
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=60, check=False)
    except subprocess.TimeoutExpired:
        return None
    if result.returncode != 0 or len(result.stdout) != w * h * 3:
        return None
    return np.frombuffer(result.stdout, dtype=np.uint8).reshape(h, w, 3)
