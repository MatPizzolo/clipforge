"""Settings loaded from the environment / `.env`, plus the price table used for cost estimates.

Secrets are `SecretStr` so they never show up in reprs or logs (CLAUDE.md rule 8).
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from clipforge.models import Permission
from clipforge.schedule import (
    DEFAULT_SLOTS,
    normalize_hashtags,
    normalize_slots,
    schedule_problem,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
log = logging.getLogger(__name__)


class TokenPrice(BaseModel):
    """USD per million tokens."""

    input: float
    output: float


class Prices(BaseModel):
    """Prices for cost estimates. Update when providers change them.

    Sources (checked 2026-09-23): Anthropic model table (claude-haiku-4-5: $1 / $5 per MTok);
    Modal pricing page for GPU per-second rates (verify at https://modal.com/pricing).
    """

    llm_per_mtok: dict[str, TokenPrice] = Field(
        default_factory=lambda: {"claude-haiku-4-5": TokenPrice(input=1.00, output=5.00)}
    )
    gpu_per_second: dict[str, float] = Field(
        default_factory=lambda: {"L4": 0.80 / 3600, "A10G": 1.10 / 3600}
    )

    def llm_usd(self, model: str, input_tokens: int, output_tokens: int) -> float:
        price = self.llm_per_mtok.get(model)
        if price is None:
            raise KeyError(f"no price for LLM model {model!r}; add it to Prices.llm_per_mtok")
        return (input_tokens * price.input + output_tokens * price.output) / 1_000_000

    def gpu_usd(self, gpu_type: str, seconds: float) -> float:
        rate = self.gpu_per_second.get(gpu_type)
        if rate is None:
            raise KeyError(f"no price for GPU {gpu_type!r}; add it to Prices.gpu_per_second")
        return seconds * rate


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    # Secrets (in production: the Modal secret `clipforge-secrets`, ADR-9)
    anthropic_api_key: SecretStr | None = None
    telegram_bot_token: SecretStr | None = None
    telegram_webhook_secret: SecretStr | None = None
    telegram_allowed_user_ids: Annotated[list[int], NoDecode] = []
    api_token: SecretStr | None = None  # bearer token for the job API
    download_signing_key: SecretStr | None = None  # HMAC key for zip links (ADR-13)

    # Deployed API (used by the CLI and in download links)
    api_url: str | None = None
    download_link_ttl_s: int = 7 * 24 * 3600

    # Models
    highlight_model: str = "claude-haiku-4-5"
    whisper_model: str = "large-v3-turbo"
    modal_app_name: str = "clipforge"

    # Job defaults
    # None/"auto" = every candidate scoring at least default_min_score (at most 30)
    default_clip_count: Annotated[int | None, NoDecode] = Field(None, ge=1, le=30)
    default_min_score: float = Field(0.80, ge=0.0, le=1.0)
    default_clip_len: Annotated[tuple[float, float], NoDecode] = (30.0, 60.0)
    default_permission: Permission = Permission.OWN

    # Posting assistant (ADR-23): off until POSTING_CHAT_ID is set
    posting_chat_id: int | None = None
    posting_timezone: str = "America/New_York"  # the audience's time zone
    posting_slots: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: list(DEFAULT_SLOTS)
    )
    posting_hashtags: Annotated[list[str], NoDecode] = []  # without "#"
    # Why posting is off despite POSTING_CHAT_ID (set by the check below; not an env value)
    posting_problem: str | None = None

    # Durable state (ADR-26, S1): Neon's pooled URL; reads come from `state_reads` (ADR-41)
    database_url: SecretStr | None = None
    state_reads: Literal["dict", "postgres"] = "dict"
    # The account the Dict queue and the POSTING_* settings belong to (dict mode, seeding)
    posting_account_id: str = "realtalk-clips-en"
    blueprints_dir: Path = _REPO_ROOT / "blueprints"

    # Limits checked in ingest, before any GPU time (ADR-15)
    max_source_duration_s: float = 3 * 3600
    max_source_bytes: int = 4_000_000_000

    # Storage: the Modal Volume mount (tests use a temp dir)
    jobs_root: Path = Path("/jobs")

    # Files the stages read (Plan 3 adds these directories to the Modal image)
    prompts_dir: Path = _REPO_ROOT / "prompts"
    fonts_dir: Path = _REPO_ROOT / "assets" / "fonts"
    models_dir: Path = _REPO_ROOT / "assets" / "models"  # YuNet face model (ADR-19)

    # Reframe (ADR-19): ffmpeg scene score above which a frame starts a new shot
    scene_threshold: float = Field(0.2, gt=0.0, lt=1.0)

    # Transcription (ADR-11): weights baked into the GPU image at this path
    whisper_model_path: str = "/models/large-v3-turbo"
    gpu_type: str = "L4"

    # Highlights: parallel LLM calls per job
    llm_max_workers: int = 4

    # Recorded in metadata.json (set by the deploy)
    git_sha: str | None = None

    prices: Prices = Field(default_factory=Prices)

    @field_validator("telegram_allowed_user_ids", mode="before")
    @classmethod
    def _split_ids(cls, value: object) -> object:
        if isinstance(value, str):
            return [int(part) for part in value.split(",") if part.strip()]
        return value

    @field_validator("default_clip_count", mode="before")
    @classmethod
    def _parse_count(cls, value: object) -> object:
        if isinstance(value, str) and value.strip().lower() in ("", "auto"):
            return None
        return value

    @field_validator("default_clip_len", mode="before")
    @classmethod
    def _parse_len(cls, value: object) -> object:
        if isinstance(value, str):
            low, sep, high = value.partition("-")
            if not sep:
                raise ValueError("expected '<min>-<max>', e.g. '30-60'")
            return (float(low), float(high))
        return value

    @field_validator("default_clip_len")
    @classmethod
    def _check_len(cls, value: tuple[float, float]) -> tuple[float, float]:
        if not 0 < value[0] < value[1]:
            raise ValueError("clip length must satisfy 0 < min < max")
        return value

    @field_validator("posting_slots", "posting_hashtags", mode="before")
    @classmethod
    def _split_list(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("posting_chat_id", mode="before")
    @classmethod
    def _empty_chat_is_off(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("posting_slots", mode="after")
    @classmethod
    def _pad_slots(cls, value: list[str]) -> list[str]:
        return normalize_slots(value)

    @field_validator("posting_hashtags", mode="after")
    @classmethod
    def _strip_hash(cls, value: list[str]) -> list[str]:
        return normalize_hashtags(value)

    @model_validator(mode="after")
    def _check_posting(self) -> Self:
        """A posting mistake turns posting off (with the reason in /status), never the app:
        every Modal step and the CLI load these settings (spec §10)."""
        problem = _posting_problem(self)
        if problem is not None:
            log.warning("posting is off: %s", problem)
            self.posting_problem = problem
            self.posting_chat_id = None
            self.posting_timezone = "America/New_York"
            self.posting_slots = list(DEFAULT_SLOTS)
            self.posting_hashtags = []
        return self


def _posting_problem(settings: Settings) -> str | None:
    problem = schedule_problem(
        settings.posting_timezone, settings.posting_slots, settings.posting_hashtags
    )
    if problem is not None:
        field, message = problem
        return f"POSTING_{field.upper()}: {message}"
    chat = settings.posting_chat_id
    if chat is not None and chat not in settings.telegram_allowed_user_ids:
        return "POSTING_CHAT_ID must be one of TELEGRAM_ALLOWED_USER_IDS"
    return None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
