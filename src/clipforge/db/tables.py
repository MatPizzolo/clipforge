"""SQLAlchemy Core tables (spec §3). Contract parts that are only read whole live in jsonb and
are validated by pydantic on the way out. One writer per column group (ADR-14, ADR-41)."""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
)  # fmt: skip
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()
JSONB_ = JSON().with_variant(JSONB(), "postgresql")
TS = DateTime(timezone=True)

accounts = Table(
    "accounts", metadata,
    Column("id", String(40), primary_key=True),
    Column("blueprint", Text, nullable=False),
    Column("blueprint_version", Integer, nullable=False),
    Column("kind", Text, nullable=False),
    Column("language", String(8), nullable=False),
    Column("niche", Text, nullable=False),
    Column("review_tier", Text, nullable=False),
    Column("persona_id", Text),  # FK to personas arrives with the table in S8
    Column("paired_account_id", String(40), ForeignKey("accounts.id")),
    Column("monthly_budget_usd", Float, nullable=False),
    Column("platforms", JSONB_, nullable=False),
    Column("brand", JSONB_, nullable=False),
    Column("posting", JSONB_, nullable=False),
    Column("created_at", TS, nullable=False),
    Column("updated_at", TS, nullable=False),
)  # fmt: skip

posting_state = Table(
    "posting_state", metadata,
    Column("account_id", String(40), ForeignKey("accounts.id"), primary_key=True),
    Column("paused", Boolean, nullable=False),
    Column("changed_at", TS, nullable=False),
)  # fmt: skip

sources = Table(
    "sources", metadata,
    Column("id", String(40), primary_key=True),
    Column("account_id", String(40), ForeignKey("accounts.id"), nullable=False),
    Column("kind", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("credit_name", Text, nullable=False),
    Column("creator_handles", JSONB_, nullable=False),
    Column("url", Text),
    Column("permission", JSONB_, nullable=False),
    Column("campaign", JSONB_),
    Column("notes", Text, nullable=False),
    Column("created_at", TS, nullable=False),
    Column("updated_at", TS, nullable=False),
)  # fmt: skip

source_events = Table(
    "source_events", metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column("source_id", String(40), ForeignKey("sources.id"), nullable=False),
    Column("at", TS, nullable=False),
    Column("actor", Text, nullable=False),
    Column("action", Text, nullable=False),
    Column("before", JSONB_),
    Column("after", JSONB_, nullable=False),
    Index("ix_source_events_source", "source_id"),
)  # fmt: skip

# No FK to sources: a job's row is written best-effort before its source may be synced.
jobs = Table(
    "jobs", metadata,
    Column("job_id", String(40), primary_key=True),
    Column("source_id", String(40)),
    Column("status", Text, nullable=False),
    Column("source_label", Text),
    Column("input", JSONB_, nullable=False),
    Column("created_at", TS, nullable=False),
    Column("updated_at", TS, nullable=False),
    Column("finished_at", TS),
    Column("cost_usd", Float, nullable=False),
    Column("metadata_path", Text),
    Column("build", Text),
    Index("ix_jobs_source_status", "source_id", "status"),
)  # fmt: skip

# job_id has no FK either: the import may run before the jobs backfill.
content_items = Table(
    "content_items", metadata,
    Column("id", String(64), primary_key=True),
    Column("account_id", String(40), ForeignKey("accounts.id"), nullable=False),
    Column("source_id", String(40), ForeignKey("sources.id")),
    Column("job_id", String(40)),
    Column("producer", Text, nullable=False),
    Column("producer_version", Text, nullable=False),
    Column("language", String(8), nullable=False),
    Column("media_kind", Text, nullable=False),
    Column("video_path", Text),
    Column("image_paths", JSONB_, nullable=False),
    Column("duration", Float),
    Column("title", Text, nullable=False),
    Column("hook", Text, nullable=False),
    Column("score", Float, nullable=False),
    Column("credits", JSONB_, nullable=False),
    Column("ai_disclosure", Boolean, nullable=False),
    Column("sponsored", Boolean, nullable=False),
    Column("cost_usd", Float, nullable=False),
    Column("parent_item_id", String(64), ForeignKey("content_items.id")),
    Column("clip_id", Text),
    Column("source_hash", String(64)),
    Column("start_s", Float),
    Column("end_s", Float),
    Column("episode", Text),
    Column("episode_finished_at", TS),
    Column("queued_at", TS, nullable=False),
    Column("unavailable_at", TS),
    Column("verdict_kind", Text),
    Column("verdict_at", TS),
    Column("verdict_reason", Text),
    Index("ix_items_account", "account_id"),
    Index("ix_items_source_hash", "source_hash"),
)  # fmt: skip

assets = Table(
    "assets", metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column("item_id", String(64), ForeignKey("content_items.id"), nullable=False),
    Column("kind", Text, nullable=False),
    Column("license", Text, nullable=False),
    Column("attribution", Text),
    Column("url", Text),
    Column("model", Text),
    Index("ix_assets_item", "item_id"),
)  # fmt: skip

posts = Table(
    "posts", metadata,
    Column("item_id", String(64), ForeignKey("content_items.id"), primary_key=True),
    Column("platform", String(16), primary_key=True),
    Column("posted_at", TS),
    Column("external_id", Text),
    Column("url", Text),
)  # fmt: skip

sends = Table(
    "sends", metadata,
    Column("item_id", String(64), ForeignKey("content_items.id"), primary_key=True),
    Column("n", Integer, primary_key=True),
    Column("at", TS, nullable=False),
    Column("slot", TS),
    Column("chat_id", BigInteger),
    Column("message_id", BigInteger, nullable=False),
    Column("video_message_id", BigInteger, nullable=False),
)  # fmt: skip

post_events = Table(
    "post_events", metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column("item_id", String(64), ForeignKey("content_items.id"), nullable=False),
    Column("platform", String(16)),
    Column("kind", Text, nullable=False),
    Column("at", TS, nullable=False),
    Column("data", JSONB_, nullable=False),
    Index("ix_post_events_item", "item_id"),
)  # fmt: skip

costs = Table(
    "costs", metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column("job_id", String(40), ForeignKey("jobs.job_id"), nullable=False),
    Column("stage", Text, nullable=False),
    Column("clip_id", Text),
    Column("wall_s", Float, nullable=False),
    Column("gpu_s", Float, nullable=False),
    Column("gpu_type", Text),
    Column("llm_model", Text),
    Column("llm_input_tokens", Integer, nullable=False),
    Column("llm_output_tokens", Integer, nullable=False),
    Column("llm_calls", Integer, nullable=False),
    Column("usd", Float, nullable=False),
    Column("cached", Boolean, nullable=False),
    Index("ix_costs_job", "job_id"),
)  # fmt: skip
