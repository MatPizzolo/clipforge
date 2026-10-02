import io
import wave
from pathlib import Path

import pytest

from clipforge.doctor import (
    audio_wav_bytes,
    configured_zones,
    format_checks,
    local_checks,
    timezone_check,
)
from tests.conftest import TALKING_HEAD, requires_ffmpeg


@requires_ffmpeg
def test_local_checks_pass_required() -> None:
    checks = local_checks()
    names = {c.name for c in checks}
    assert {"ffmpeg", "libass (ass filter)", "libx264", "h264_nvenc", "timeline filters"} <= names
    assert all(c.ok for c in checks if c.required), format_checks(checks)


@requires_ffmpeg
def test_audio_wav_bytes_is_16k_mono() -> None:
    with wave.open(io.BytesIO(audio_wav_bytes(TALKING_HEAD))) as wav:
        assert wav.getnchannels() == 1
        assert wav.getframerate() == 16000
        assert 9.9 < wav.getnframes() / 16000 < 10.1


def test_timezone_check_passes_for_real_zones() -> None:
    check = timezone_check(["America/New_York", "Europe/Madrid", "UTC"])
    assert check.ok and check.required
    assert check.detail == "America/New_York, Europe/Madrid, UTC load"


def test_timezone_check_fails_on_a_zone_that_does_not_load() -> None:
    check = timezone_check(["America/New_York", "Mars/Olympus", "UTC"])
    assert not check.ok and check.required
    assert "Mars/Olympus" in check.detail and "tzdata" in check.detail
    assert "[FAIL] time zones" in format_checks([check])


def test_timezone_check_rejects_a_path_like_name() -> None:
    assert not timezone_check(["../etc/passwd"]).ok


def test_timezone_check_fails_on_a_tzdata_folder() -> None:
    """`America` is a folder in tzdata: ZoneInfo raises IsADirectoryError, an OSError."""
    check = timezone_check(["America", "UTC"])
    assert not check.ok and "America" in check.detail


def test_configured_zones_reads_the_raw_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The raw POSTING_TIMEZONE, not config.Settings' fallback, which hides a bad value."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("POSTING_TIMEZONE", raising=False)
    monkeypatch.delenv("OWNER_TIMEZONE", raising=False)
    (tmp_path / ".env").write_text("POSTING_TIMEZONE=Mars/Olympus\nOWNER_TIMEZONE=\n")
    assert configured_zones() == ["Mars/Olympus", "UTC"]
    monkeypatch.setenv("OWNER_TIMEZONE", "Europe/Madrid")
    assert configured_zones() == ["Mars/Olympus", "Europe/Madrid", "UTC"]
