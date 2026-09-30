"""initial S1 schema (spec §3). Frozen: explicit DDL, so later edits to db/tables.py never
change what this revision builds (add a new revision instead).

Revision ID: 0001
Revises:
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

JSONB_ = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("blueprint", sa.Text(), nullable=False),
        sa.Column("blueprint_version", sa.Integer(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("niche", sa.Text(), nullable=False),
        sa.Column("review_tier", sa.Text(), nullable=False),
        sa.Column("persona_id", sa.Text(), nullable=True),
        sa.Column("paired_account_id", sa.String(length=40), nullable=True),
        sa.Column("monthly_budget_usd", sa.Float(), nullable=False),
        sa.Column("platforms", JSONB_, nullable=False),
        sa.Column("brand", JSONB_, nullable=False),
        sa.Column("posting", JSONB_, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["paired_account_id"],
            ["accounts.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "jobs",
        sa.Column("job_id", sa.String(length=40), nullable=False),
        sa.Column("source_id", sa.String(length=40), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("source_label", sa.Text(), nullable=True),
        sa.Column("input", JSONB_, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("metadata_path", sa.Text(), nullable=True),
        sa.Column("build", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("job_id"),
    )
    op.create_index("ix_jobs_source_status", "jobs", ["source_id", "status"], unique=False)
    op.create_table(
        "costs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("job_id", sa.String(length=40), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("clip_id", sa.Text(), nullable=True),
        sa.Column("wall_s", sa.Float(), nullable=False),
        sa.Column("gpu_s", sa.Float(), nullable=False),
        sa.Column("gpu_type", sa.Text(), nullable=True),
        sa.Column("llm_model", sa.Text(), nullable=True),
        sa.Column("llm_input_tokens", sa.Integer(), nullable=False),
        sa.Column("llm_output_tokens", sa.Integer(), nullable=False),
        sa.Column("llm_calls", sa.Integer(), nullable=False),
        sa.Column("usd", sa.Float(), nullable=False),
        sa.Column("cached", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.job_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_costs_job", "costs", ["job_id"], unique=False)
    op.create_table(
        "posting_state",
        sa.Column("account_id", sa.String(length=40), nullable=False),
        sa.Column("paused", sa.Boolean(), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
        ),
        sa.PrimaryKeyConstraint("account_id"),
    )
    op.create_table(
        "sources",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("account_id", sa.String(length=40), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("credit_name", sa.Text(), nullable=False),
        sa.Column("creator_handles", JSONB_, nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("permission", JSONB_, nullable=False),
        sa.Column("campaign", JSONB_, nullable=True),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "content_items",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("account_id", sa.String(length=40), nullable=False),
        sa.Column("source_id", sa.String(length=40), nullable=True),
        sa.Column("job_id", sa.String(length=40), nullable=True),
        sa.Column("producer", sa.Text(), nullable=False),
        sa.Column("producer_version", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("media_kind", sa.Text(), nullable=False),
        sa.Column("video_path", sa.Text(), nullable=True),
        sa.Column("image_paths", JSONB_, nullable=False),
        sa.Column("duration", sa.Float(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("hook", sa.Text(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("credits", JSONB_, nullable=False),
        sa.Column("ai_disclosure", sa.Boolean(), nullable=False),
        sa.Column("sponsored", sa.Boolean(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("parent_item_id", sa.String(length=64), nullable=True),
        sa.Column("clip_id", sa.Text(), nullable=True),
        sa.Column("source_hash", sa.String(length=64), nullable=True),
        sa.Column("start_s", sa.Float(), nullable=True),
        sa.Column("end_s", sa.Float(), nullable=True),
        sa.Column("episode", sa.Text(), nullable=True),
        sa.Column("episode_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("unavailable_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verdict_kind", sa.Text(), nullable=True),
        sa.Column("verdict_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verdict_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
        ),
        sa.ForeignKeyConstraint(
            ["parent_item_id"],
            ["content_items.id"],
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_items_account", "content_items", ["account_id"], unique=False)
    op.create_index("ix_items_source_hash", "content_items", ["source_hash"], unique=False)
    op.create_table(
        "source_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("source_id", sa.String(length=40), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("before", JSONB_, nullable=True),
        sa.Column("after", JSONB_, nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_source_events_source", "source_events", ["source_id"], unique=False)
    op.create_table(
        "assets",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("item_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("license", sa.Text(), nullable=False),
        sa.Column("attribution", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["content_items.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_assets_item", "assets", ["item_id"], unique=False)
    op.create_table(
        "post_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("item_id", sa.String(length=64), nullable=False),
        sa.Column("platform", sa.String(length=16), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", JSONB_, nullable=False),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["content_items.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_post_events_item", "post_events", ["item_id"], unique=False)
    op.create_table(
        "posts",
        sa.Column("item_id", sa.String(length=64), nullable=False),
        sa.Column("platform", sa.String(length=16), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["content_items.id"],
        ),
        sa.PrimaryKeyConstraint("item_id", "platform"),
    )
    op.create_table(
        "sends",
        sa.Column("item_id", sa.String(length=64), nullable=False),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("slot", sa.DateTime(timezone=True), nullable=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=True),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("video_message_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["content_items.id"],
        ),
        sa.PrimaryKeyConstraint("item_id", "n"),
    )


def downgrade() -> None:
    op.drop_table("sends")
    op.drop_table("posts")
    op.drop_index("ix_post_events_item", table_name="post_events")
    op.drop_table("post_events")
    op.drop_index("ix_assets_item", table_name="assets")
    op.drop_table("assets")
    op.drop_index("ix_source_events_source", table_name="source_events")
    op.drop_table("source_events")
    op.drop_index("ix_items_source_hash", table_name="content_items")
    op.drop_index("ix_items_account", table_name="content_items")
    op.drop_table("content_items")
    op.drop_table("sources")
    op.drop_table("posting_state")
    op.drop_index("ix_costs_job", table_name="costs")
    op.drop_table("costs")
    op.drop_index("ix_jobs_source_status", table_name="jobs")
    op.drop_table("jobs")
    op.drop_table("accounts")
