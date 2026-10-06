from pathlib import Path

import pytest
from pydantic import ValidationError

from clipforge.config import Prices, Settings
from tests.bot.fakes import ALLOWED_USER, make_settings

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "DATABASE_URL",
        "STATE_READS",
        "ANTHROPIC_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_ALLOWED_USER_IDS",
        "API_TOKEN",
        "DOWNLOAD_SIGNING_KEY",
        "TELEGRAM_WEBHOOK_SECRET",
        "API_URL",
    ):
        monkeypatch.delenv(name, raising=False)


def test_defaults_without_env_file() -> None:
    s = Settings(_env_file=None)
    assert s.highlight_model == "claude-haiku-4-5"
    assert s.default_clip_len == (30.0, 60.0)
    assert s.default_permission == "own"
    assert s.telegram_allowed_user_ids == []
    assert s.anthropic_api_key is None


def test_env_example_parses() -> None:
    s = Settings(_env_file=REPO_ROOT / ".env.example")
    assert s.telegram_allowed_user_ids == []
    assert s.jobs_root == Path("/jobs")
    assert s.api_token is None
    assert s.max_source_duration_s == 10800


def test_serverless_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_TOKEN", "tok-secret")
    monkeypatch.setenv("DOWNLOAD_SIGNING_KEY", "sign-secret")
    s = Settings(_env_file=None)
    assert s.jobs_root == Path("/jobs")
    assert s.download_link_ttl_s == 7 * 24 * 3600
    assert s.max_source_bytes == 4_000_000_000
    assert s.api_url is None
    assert s.api_token is not None and s.api_token.get_secret_value() == "tok-secret"
    assert "tok-secret" not in repr(s) and "sign-secret" not in repr(s)
    assert not hasattr(s, "transcribe_backend")


def test_env_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "123, 456")
    monkeypatch.setenv("DEFAULT_CLIP_LEN", "20-45")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-secret")
    s = Settings(_env_file=None)
    assert s.telegram_allowed_user_ids == [123, 456]
    assert s.default_clip_len == (20.0, 45.0)
    assert s.anthropic_api_key is not None
    assert s.anthropic_api_key.get_secret_value() == "sk-test-secret"
    assert "sk-test-secret" not in repr(s)


@pytest.mark.parametrize("value", ["60-30", "30", "0-10"])
def test_bad_clip_len(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("DEFAULT_CLIP_LEN", value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_bad_permission(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEFAULT_PERMISSION", "found_it_online")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_prices() -> None:
    p = Prices()
    # 30k input + 6k output on Haiku 4.5 = 0.03 + 0.03
    assert p.llm_usd("claude-haiku-4-5", 30_000, 6_000) == pytest.approx(0.06)
    assert p.gpu_usd("L4", 3600) == pytest.approx(0.80)
    with pytest.raises(KeyError):
        p.llm_usd("unknown-model", 1, 1)


def test_asset_paths_and_gpu_defaults() -> None:
    s = Settings(_env_file=None)
    assert (s.prompts_dir / "highlights_v1.md").is_file()
    assert (s.prompts_dir / "metadata.json").is_file()
    assert (s.fonts_dir / "Anton-Regular.ttf").is_file()
    assert s.whisper_model_path == "/models/large-v3-turbo"
    assert s.gpu_type == "L4" and s.llm_max_workers == 4 and s.git_sha is None


def test_clip_count_defaults_to_auto(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEFAULT_CLIP_COUNT", raising=False)
    s = Settings(_env_file=None)
    assert s.default_clip_count is None and s.default_min_score == 0.80
    monkeypatch.setenv("DEFAULT_CLIP_COUNT", "auto")
    assert Settings(_env_file=None).default_clip_count is None
    monkeypatch.setenv("DEFAULT_CLIP_COUNT", "7")
    monkeypatch.setenv("DEFAULT_MIN_SCORE", "0.85")
    s = Settings(_env_file=None)
    assert s.default_clip_count == 7 and s.default_min_score == 0.85


def test_reframe_settings() -> None:
    s = Settings(_env_file=None)
    assert s.scene_threshold == 0.2
    assert (s.models_dir / "face_detection_yunet_2023mar.onnx").is_file()


def test_posting_settings_parse_env_strings(tmp_path: Path) -> None:
    s = make_settings(
        tmp_path, posting_chat_id=ALLOWED_USER, posting_slots="09:00, 18:30",
        posting_hashtags="mindset,growth", posting_timezone="Europe/Madrid",
    )  # fmt: skip
    assert s.posting_slots == ["09:00", "18:30"]
    assert s.posting_hashtags == ["mindset", "growth"]


def test_posting_settings_are_normalized(tmp_path: Path) -> None:
    s = make_settings(tmp_path, posting_slots="8:00, 18:30", posting_hashtags="#mindset,growth")
    assert s.posting_slots == ["08:00", "18:30"]
    assert s.posting_hashtags == ["mindset", "growth"]


@pytest.mark.parametrize(
    ("overrides", "problem"),
    [
        ({"posting_timezone": "Mars/Olympus"}, "time zone"),
        ({"posting_timezone": "America"}, "time zone"),  # a tzdata folder: IsADirectoryError
        ({"posting_slots": "9am"}, "HH:MM"),
        ({"posting_slots": "18:00,09:00"}, "in order"),
        ({"posting_slots": ""}, "slots"),
        ({"posting_hashtags": "mind set"}, "hashtags"),
        ({"posting_chat_id": 999}, "TELEGRAM_ALLOWED_USER_IDS"),  # not an allowed user
    ],
)
def test_bad_posting_settings_turn_posting_off_not_the_app(
    tmp_path: Path, overrides: dict[str, object], problem: str
) -> None:
    # a posting typo in the Modal secret must not stop every pipeline step from starting
    s = make_settings(tmp_path, **{"posting_chat_id": ALLOWED_USER, **overrides})
    assert s.posting_chat_id is None
    assert s.posting_problem is not None and problem in s.posting_problem
    assert s.posting_slots and s.posting_timezone  # safe defaults for the slot code


def test_empty_posting_chat_id_means_off(tmp_path: Path) -> None:
    # `.env.example` ships `POSTING_CHAT_ID=`; copying it as-is must not break the settings
    assert make_settings(tmp_path, posting_chat_id="").posting_chat_id is None


def test_database_and_state_settings(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        jobs_root=tmp_path,
        database_url="postgresql://u:s3cr3tpw@host.neon.tech/db?sslmode=require",
        state_reads="postgres",
    )
    assert settings.state_reads == "postgres"
    assert settings.database_url is not None
    assert "s3cr3tpw" not in repr(settings)
    assert settings.posting_account_id == "realtalk-clips-en"
    assert (settings.blueprints_dir / "realtalk-clips.toml").name == "realtalk-clips.toml"
    defaults = Settings(_env_file=None, jobs_root=tmp_path)  # type: ignore[call-arg]
    assert defaults.state_reads == "dict" and defaults.database_url is None


@pytest.mark.parametrize("value", ["postgress", "sql", "Postgres "])
def test_a_bad_state_reads_turns_posting_off_not_the_app(tmp_path: Path, value: str) -> None:
    # card 039 / rollout 010: `STATE_READS=postgress` failed every container for 5 minutes
    s = make_settings(tmp_path, posting_chat_id=ALLOWED_USER, state_reads=value)
    if value.strip().lower() == "postgres":  # case and spaces are forgiven
        assert s.state_reads == "postgres" and s.state_reads_problem is None
        return
    assert s.state_reads == "dict"  # the Dict is still written on every action (ADR-41)
    assert s.state_reads_problem == f"STATE_READS must be dict or postgres, got {value!r}"
    assert s.posting_problem == s.state_reads_problem
    assert s.posting_chat_id is None


def test_a_bad_state_reads_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STATE_READS", "postgress")
    s = Settings(_env_file=None, jobs_root=tmp_path)  # type: ignore[call-arg]
    assert s.state_reads == "dict"
    assert s.state_reads_problem is not None and "postgress" in s.state_reads_problem


def test_a_mangled_state_reads_is_not_echoed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # security review: a missing newline can put a connection string in the value
    monkeypatch.setenv("STATE_READS", "postgres DATABASE_URL=postgresql://u:pw@host/db")
    monkeypatch.setenv("STATE_READS_PROBLEM", "forged")
    s = Settings(_env_file=None, jobs_root=tmp_path)  # type: ignore[call-arg]
    expected = "STATE_READS must be dict or postgres, got a value of 47 characters"
    assert s.state_reads_problem == expected
    monkeypatch.setenv("STATE_READS", "dict")
    fine = Settings(_env_file=None, jobs_root=tmp_path)  # type: ignore[call-arg]
    assert fine.state_reads_problem is None


def test_dashboard_url_is_optional_and_never_breaks_settings(tmp_path: Path) -> None:
    def url(value: str | None) -> str | None:
        return Settings(_env_file=None, jobs_root=tmp_path,  # type: ignore[call-arg]
                        dashboard_url=value).dashboard_url  # fmt: skip

    assert url(None) is None and url("") is None
    assert url("https://dash.example/") == "https://dash.example"
    assert url("javascript:alert(1)") is None and url("https://a b") is None
    # security review minor 5: links and the login behind them never go over plain http,
    # except to a local dashboard
    assert url("http://dash.example") is None
    assert url("http://localhost:3000") == "http://localhost:3000"
    assert url("http://127.0.0.1:3000/") == "http://127.0.0.1:3000"
