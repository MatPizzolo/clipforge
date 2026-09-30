import io
import wave

from clipforge.doctor import audio_wav_bytes, format_checks, local_checks
from tests.conftest import TALKING_HEAD, requires_ffmpeg


@requires_ffmpeg
def test_local_checks_pass_required() -> None:
    checks = local_checks()
    names = {c.name for c in checks}
    assert {"ffmpeg", "libass (ass filter)", "libx264", "h264_nvenc"} <= names
    assert all(c.ok for c in checks if c.required), format_checks(checks)


@requires_ffmpeg
def test_audio_wav_bytes_is_16k_mono() -> None:
    with wave.open(io.BytesIO(audio_wav_bytes(TALKING_HEAD))) as wav:
        assert wav.getnchannels() == 1
        assert wav.getframerate() == 16000
        assert 9.9 < wav.getnframes() / 16000 < 10.1
