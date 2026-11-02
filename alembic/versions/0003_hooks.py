"""The hook library (ADR-50, hooks spec §3): patterns, their append-only versions, per-account
weights, experiment freezes, ratings and events, plus the stamp columns on `content_items`.
Expand-only, explicit DDL (frozen once it lands, like 0001 and 0002), so S2a's code runs on it
unchanged (the HK-1 rollback). It carries none of 0002's deferred items.

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

JSONB_ = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
TS = sa.DateTime(timezone=True)

# Copied from 0002_s2.py (migrations never import each other); tests pin the two equal
ACTOR_RE = (
    r"^(telegram:[0-9]{1,20}|web:[A-Za-z0-9-]{1,39}|session:[a-z0-9][a-z0-9-]{0,39}"
    r"|cli:[A-Za-z0-9._-]{1,32}|system:[a-z]([a-z-]{0,38}[a-z])?)$"
)
ACTOR_CHECK = f"actor ~ '{ACTOR_RE}' and length(actor) <= 80"
STATUSES = ("draft", "approved", "retired")
APPEND_ONLY = ("hook_pattern_versions", "hook_events")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} in ({', '.join(repr(v) for v in values)})"


def _append_only(table: str) -> None:
    op.execute(f"""create function {table}_append_only() returns trigger
                   language plpgsql as $$ begin
                     raise exception '{table} is append-only';
                   end $$""")
    op.execute(f"""create trigger {table}_no_change before update or delete on {table}
                   for each row execute function {table}_append_only()""")


def upgrade() -> None:
    op.create_table(
        "hook_patterns",
        sa.Column("id", sa.String(length=16), primary_key=True),
        sa.Column("account_id", sa.String(length=40), sa.ForeignKey("accounts.id"),
                  nullable=True),
        sa.Column("blueprint_name", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("control", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.CheckConstraint("(account_id is null) <> (blueprint_name is null)",
                           name="ck_hook_patterns_scope"),
        sa.CheckConstraint(_in("status", STATUSES), name="ck_hook_patterns_status"),
    )  # fmt: skip
    op.create_index("ix_hook_patterns_account", "hook_patterns", ["account_id"])
    op.create_index("ix_hook_patterns_blueprint", "hook_patterns", ["blueprint_name"])
    op.create_table(
        "hook_pattern_versions",
        sa.Column("pattern_id", sa.String(length=16), sa.ForeignKey("hook_patterns.id"),
                  primary_key=True),
        sa.Column("n", sa.Integer(), primary_key=True),
        sa.Column("data", JSONB_, nullable=False),
        sa.Column("author", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.CheckConstraint(ACTOR_CHECK.replace("actor", "author"),
                           name="ck_hook_versions_author"),
    )  # fmt: skip
    op.create_table(
        "hook_weights",
        sa.Column("account_id", sa.String(length=40), sa.ForeignKey("accounts.id"),
                  primary_key=True),
        sa.Column("pattern_id", sa.String(length=16), sa.ForeignKey("hook_patterns.id"),
                  primary_key=True),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("updated_by", sa.Text(), nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.CheckConstraint("weight >= 0", name="ck_hook_weights_nonneg"),
        sa.CheckConstraint(ACTOR_CHECK.replace("actor", "updated_by"),
                           name="ck_hook_weights_updated_by"),
    )  # fmt: skip
    op.create_table(
        "hook_freezes",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("account_id", sa.String(length=40), sa.ForeignKey("accounts.id"),
                  nullable=False),
        sa.Column("experiment_id", sa.BigInteger(), nullable=False),  # S3c's experiments.id
        sa.Column("rotation", JSONB_, nullable=False),  # HookRotation
        sa.Column("frozen_at", TS, nullable=False),
        sa.Column("frozen_by", sa.Text(), nullable=False),
        sa.Column("released_at", TS, nullable=True),
        sa.Column("released_by", sa.Text(), nullable=True),
        sa.CheckConstraint(ACTOR_CHECK.replace("actor", "frozen_by"),
                           name="ck_hook_freezes_frozen_by"),
        sa.CheckConstraint(
            "released_by is null or (" + ACTOR_CHECK.replace("actor", "released_by") + ")",
            name="ck_hook_freezes_released_by"),
    )  # fmt: skip
    op.create_index("ux_hook_freezes_open", "hook_freezes", ["account_id"], unique=True,
                    postgresql_where=sa.text("released_at is null"))  # fmt: skip
    op.create_table(
        "hook_ratings",
        sa.Column("item_id", sa.String(length=64), sa.ForeignKey("content_items.id"),
                  primary_key=True),
        sa.Column("rating", sa.SmallInteger(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("at", TS, nullable=False),
        sa.CheckConstraint("rating in (-1, 1)", name="ck_hook_ratings_value"),
        sa.CheckConstraint(ACTOR_CHECK, name="ck_hook_ratings_actor"),
    )  # fmt: skip
    op.create_table(
        "hook_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("at", TS, nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("account_id", sa.String(length=40), sa.ForeignKey("accounts.id"),
                  nullable=True),
        sa.Column("pattern_id", sa.String(length=16), sa.ForeignKey("hook_patterns.id"),
                  nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("data", JSONB_, nullable=False),
        sa.CheckConstraint(ACTOR_CHECK, name="ck_hook_events_actor"),
    )  # fmt: skip
    op.create_index("ix_hook_events_pattern", "hook_events", ["pattern_id", "at"])
    for table in APPEND_ONLY:
        _append_only(table)

    # ---- the stamp on items (written once, at enqueue) and the re-render link (HK-2)
    op.add_column("content_items", sa.Column("hook_pattern_id", sa.String(length=16),
                                             nullable=True))  # fmt: skip
    op.add_column("content_items", sa.Column("hook_version", sa.Integer(), nullable=True))
    op.add_column("content_items", sa.Column("hook_weights", JSONB_, nullable=True))
    op.add_column("content_items", sa.Column("hook_result", JSONB_, nullable=True))
    op.add_column("content_items", sa.Column("superseded_by", sa.String(length=64),
                                             nullable=True))  # fmt: skip
    op.create_foreign_key("fk_items_superseded_by", "content_items", "content_items",
                          ["superseded_by"], ["id"])  # fmt: skip
    op.create_foreign_key("fk_items_hook_version", "content_items", "hook_pattern_versions",
                          ["hook_pattern_id", "hook_version"], ["pattern_id", "n"])  # fmt: skip
    op.create_index("ix_items_hook_pattern", "content_items", ["hook_pattern_id"])


def downgrade() -> None:
    op.drop_index("ix_items_hook_pattern", table_name="content_items")
    op.drop_constraint("fk_items_hook_version", "content_items", type_="foreignkey")
    op.drop_constraint("fk_items_superseded_by", "content_items", type_="foreignkey")
    for name in ("superseded_by", "hook_result", "hook_weights", "hook_version",
                 "hook_pattern_id"):  # fmt: skip
        op.drop_column("content_items", name)
    for table in APPEND_ONLY:
        op.execute(f"drop trigger {table}_no_change on {table}")
        op.execute(f"drop function {table}_append_only()")
    op.drop_index("ix_hook_events_pattern", table_name="hook_events")
    op.drop_table("hook_events")
    op.drop_table("hook_ratings")
    op.drop_index("ux_hook_freezes_open", table_name="hook_freezes")
    op.drop_table("hook_freezes")
    op.drop_table("hook_weights")
    op.drop_table("hook_pattern_versions")
    op.drop_index("ix_hook_patterns_blueprint", table_name="hook_patterns")
    op.drop_index("ix_hook_patterns_account", table_name="hook_patterns")
    op.drop_table("hook_patterns")
