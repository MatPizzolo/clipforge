from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from clipforge.config import Settings
from clipforge.models import SourceMedia, StageName, Transcript
from clipforge.pipeline.errors import PermanentError
from clipforge.stages import transcribe
from clipforge.stages.transcribe import to_transcript
from tests.stages.helpers import FakeTranscriber, make_ctx


def seg(text: str, words: list[tuple[str, float, float]]) -> NS:
    return NS(text=text, words=[NS(word=w, start=s, end=e, probability=0.9) for w, s, e in words])


def test_to_transcript_cleans_words() -> None:
    segments = [
        seg(" Hello world.", [(" Hello", 0.0, 0.4), (" world.", 0.5, 0.9)]),
        seg(" Oops", [(" Oops", 2.0, 1.8), ("  ", 2.1, 2.2), (" early", -0.2, 0.1)]),
        seg(" ", []),
    ]
    t = to_transcript(segments, "en", 0.98, 10.0, "large-v3-turbo")
    assert [w.text for w in t.words] == ["Hello", "world.", "Oops", "early"]
    oops, early = t.words[2], t.words[3]
    assert (oops.start, oops.end) == (2.0, 2.0)  # inverted times clamped
    assert early.start == 0.0  # negative start clamped
    assert len(t.segments) == 2
    assert (t.segments[1].start, t.segments[1].end) == (0.0, 2.0)
    assert (t.language, t.model, t.duration_s) == ("en", "large-v3-turbo", 10.0)


def make_source(root: Path) -> SourceMedia:
    audio = root / "cache" / "ingest" / "k" / "audio.wav"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"RIFF")
    return SourceMedia(
        video_path="cache/ingest/k/source.mp4",
        audio_path="cache/ingest/k/audio.wav",
        source_hash="b" * 64,
        duration_s=10.0,
        fps=30.0,
        width=1920,
        height=1080,
        video_codec="h264",
        size_bytes=4,
    )


def test_run_caches_and_records_gpu_cost(tmp_path: Path, short_transcript: Transcript) -> None:
    ctx = make_ctx(tmp_path)
    fake = FakeTranscriber(short_transcript)
    settings = Settings(_env_file=None, jobs_root=tmp_path)
    source = make_source(tmp_path)
    first = transcribe.run(ctx, source, fake, settings, "en")
    second = transcribe.run(ctx, source, fake, settings, "en")
    assert first == second and fake.calls == ["en"]
    [cost, cached] = ctx.job().cost.stages
    assert cost.stage is StageName.TRANSCRIBE and cost.gpu_type == "L4" and cost.gpu_s >= 0
    assert cost.usd_estimate == pytest.approx(settings.prices.gpu_usd("L4", cost.gpu_s))
    assert cached.cached
    transcribe.run(ctx, source, fake, settings, None)  # a different language hint is a new key
    assert fake.calls == ["en", None]


def test_no_speech_is_permanent(tmp_path: Path) -> None:
    empty = Transcript(language="en", duration_s=10.0, model="fake", segments=[])
    settings = Settings(_env_file=None, jobs_root=tmp_path)
    with pytest.raises(PermanentError, match="no speech"):
        transcribe.run(
            make_ctx(tmp_path), make_source(tmp_path), FakeTranscriber(empty), settings, None
        )


@pytest.mark.gpu
def test_whisper_on_gpu(tmp_path: Path, talking_head: Path) -> None:
    """Runs where faster-whisper and CUDA exist: the Modal GPU image (Plan 3)."""
    pytest.importorskip("faster_whisper")
    from clipforge.doctor import audio_wav_bytes

    audio = tmp_path / "audio.wav"
    audio.write_bytes(audio_wav_bytes(talking_head))
    settings = Settings(_env_file=None)
    whisper = transcribe.WhisperTranscriber(settings.whisper_model_path, settings.whisper_model)
    transcript = whisper.transcribe(audio, None)
    assert transcript.language == "en" and len(transcript.words) > 10
