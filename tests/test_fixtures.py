"""Guards the fixtures themselves, so stage tests can trust them."""

import json
import subprocess
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from clipforge.models import LLMClipsResponse, Transcript
from tests.builders import PAUSE_S, sentence_bounds
from tests.conftest import MediaFactory, llm_fixture, requires_ffmpeg


def ffprobe(path: Path) -> dict[str, Any]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    result: dict[str, Any] = json.loads(out)
    return result


def streams(info: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [s for s in info["streams"] if s["codec_type"] == kind]


@requires_ffmpeg
@pytest.mark.parametrize(
    ("kwargs", "vcodec"),
    [
        ({"width": 1920, "height": 1080, "container": "mkv"}, "h264"),
        ({"width": 1080, "height": 1080}, "h264"),
        ({"width": 1080, "height": 1920}, "h264"),
        ({"vcodec": "mpeg4", "container": "mkv"}, "mpeg4"),
    ],
)
def test_synthetic_media(media: MediaFactory, kwargs: dict[str, Any], vcodec: str) -> None:
    info = ffprobe(media(**kwargs))
    video = streams(info, "video")
    assert len(video) == 1
    assert video[0]["codec_name"] == vcodec
    assert video[0]["width"] == kwargs.get("width", 320)
    assert video[0]["height"] == kwargs.get("height", 180)
    assert len(streams(info, "audio")) == 1
    assert float(info["format"]["duration"]) == pytest.approx(3.0, abs=0.1)


@requires_ffmpeg
def test_synthetic_media_without_audio(media: MediaFactory) -> None:
    assert streams(ffprobe(media(audio=False)), "audio") == []


@requires_ffmpeg
def test_synthetic_media_vfr(media: MediaFactory) -> None:
    video = streams(ffprobe(media(vfr=True)), "video")[0]
    # a third of the frames survive, and the average rate reflects it
    num, den = (int(x) for x in video["avg_frame_rate"].split("/"))
    assert num / den == pytest.approx(10, abs=1)


@requires_ffmpeg
def test_talking_head(talking_head: Path) -> None:
    info = ffprobe(talking_head)
    assert float(info["format"]["duration"]) == pytest.approx(10.0, abs=0.1)
    assert len(streams(info, "audio")) == 1
    assert talking_head.stat().st_size < 2_000_000


def test_short_transcript(short_transcript: Transcript) -> None:
    words = short_transcript.words
    assert words[-1].end <= short_transcript.duration_s
    assert all(a.end <= b.start for a, b in pairwise(words))


def test_long_transcript(long_transcript: Transcript) -> None:
    bounds = sentence_bounds(long_transcript)
    assert long_transcript.words[-1].end <= long_transcript.duration_s == 720.0
    assert len(bounds) > 150
    # every sentence is followed by at least a 300 ms silence
    gaps = [b[0] - a[1] for a, b in pairwise(bounds)]
    assert min(gaps) == pytest.approx(PAUSE_S)
    # segments must cut across sentences somewhere, like real whisper output
    assert any(not s.text.endswith((".", "?")) for s in long_transcript.segments)


def test_llm_fixtures_parse_as_intended(long_transcript: Transcript) -> None:
    valid = LLMClipsResponse.model_validate_json(llm_fixture("llm_valid.json"))
    assert len(valid.clips) == 2
    assert all(c.end <= long_transcript.duration_s for c in valid.clips)
    assert LLMClipsResponse.model_validate_json(llm_fixture("llm_empty.json")).clips == []
    out_of_range = LLMClipsResponse.model_validate_json(llm_fixture("llm_out_of_range.json"))
    assert out_of_range.clips[0].end > long_transcript.duration_s
    with pytest.raises(ValidationError):
        LLMClipsResponse.model_validate_json(llm_fixture("llm_invalid_schema.json"))
    with pytest.raises(ValidationError):
        LLMClipsResponse.model_validate_json(llm_fixture("llm_malformed.txt"))
    assert "```json" in llm_fixture("llm_fenced.txt")
