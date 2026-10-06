"""S2 (S2 spec §3): the S3 dashboard spec §8.7 deferred items, the publish columns, autopilot,
slot plans, webhook deliveries and tracking links. Expand-only, explicit DDL (frozen once it
lands, like 0001), so the S1 code runs on it unchanged (the S2a rollback).

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

JSONB_ = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
TS = sa.DateTime(timezone=True)

# The actor format (posting/actions.ACTOR): telegram:<id>, web:<login>, session:<name>,
# cli:<os user>, system:<component> (spec §2), at most 80 characters
ACTOR_RE = (
    r"^(telegram:[0-9]{1,20}|web:[A-Za-z0-9-]{1,39}|session:[a-z0-9][a-z0-9-]{0,39}"
    r"|cli:[A-Za-z0-9._-]{1,32}|system:[a-z]([a-z-]{0,38}[a-z])?)$"
)
ACTOR_CHECK = f"actor ~ '{ACTOR_RE}' and length(actor) <= 80"
POST_STATES = ("pending", "claimed", "scheduled", "retrying", "published", "failed",
               "final_failed", "cancelled")  # fmt: skip
PLAN_STATES = ("planned", "approved", "handed_off", "done", "empty", "missed")
PRESETS = ("hands_on", "supervised", "autopilot", "custom")  # custom: a control overridden
DIALS = ("review", "sample", "auto")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} in ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    # ---- the deferred items (S3 dashboard spec §8.7)
    op.add_column("jobs", sa.Column("error", sa.Text(), nullable=True))
    op.add_column("post_events", sa.Column("actor", sa.Text(), nullable=True))
    # only well-formed actors are copied (S1 wrote them through the same pattern), so the check
    # constraint below can never fail the migration on an odd old row
    op.execute(
        f"update post_events set actor = data->>'actor' "
        f"where data ? 'actor' and data->>'actor' ~ '{ACTOR_RE}' "
        f"and length(data->>'actor') <= 80"
    )
    op.create_check_constraint("ck_post_events_actor", "post_events",
                               f"actor is null or ({ACTOR_CHECK})")  # fmt: skip
    op.add_column("posting_state", sa.Column("changed_by", sa.Text(), nullable=True))
    op.add_column("posting_state", sa.Column("reason", sa.Text(), nullable=True))
    changed_by = ACTOR_CHECK.replace("actor", "changed_by")
    op.create_check_constraint("ck_posting_state_changed_by", "posting_state",
                               f"changed_by is null or ({changed_by})")  # fmt: skip

    # ---- new columns (spec §3)
    op.add_column("accounts", sa.Column("publisher", JSONB_, nullable=True))
    for name, type_ in [("copy", JSONB_), ("review_lane", sa.Text()),
                        ("review_reasons", JSONB_), ("review_dial", sa.Text()),
                        ("review_window", sa.Text()), ("gate", JSONB_), ("approved_at", TS),
                        ("approved_by", sa.Text())]:  # fmt: skip
        op.add_column("content_items", sa.Column(name, type_, nullable=True))
    for name, type_ in [("publisher", sa.Text()), ("claimed_at", TS), ("scheduled_for", TS),
                        ("handed_off_at", TS), ("request_id", sa.Text()),
                        ("upload_job_id", sa.Text()), ("error", sa.Text()),
                        ("copy", JSONB_)]:  # fmt: skip
        op.add_column("posts", sa.Column(name, type_, nullable=True))
    op.add_column("posts", sa.Column("state", sa.Text(), nullable=False,
                                     server_default="pending"))  # fmt: skip
    op.add_column("posts", sa.Column("attempts", sa.Integer(), nullable=False,
                                     server_default="0"))  # fmt: skip
    op.create_check_constraint("ck_posts_state", "posts", _in("state", POST_STATES))
    op.create_index("ix_posts_state_scheduled", "posts", ["state", "scheduled_for"])
    op.create_index("ix_posts_upload_job", "posts", ["upload_job_id"])

    # ---- new tables
    op.create_table(
        "autopilot",
        sa.Column(
            "account_id", sa.String(length=40), sa.ForeignKey("accounts.id"), primary_key=True
        ),
        sa.Column("preset", sa.Text(), nullable=False),
        sa.Column("produce", sa.Boolean(), nullable=False),
        sa.Column("review_dial", sa.Text(), nullable=False),
        sa.Column("publish", sa.Boolean(), nullable=False),
        sa.Column("scale", sa.Boolean(), nullable=False),
        sa.Column("runway_days", sa.Integer(), nullable=False),
        sa.Column("batch_line_usd", sa.Float(), nullable=False),
        sa.Column("monthly_cap_usd", sa.Float(), nullable=False),
        sa.Column("updated_by", sa.Text(), nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.CheckConstraint(_in("preset", PRESETS), name="ck_autopilot_preset"),
        sa.CheckConstraint(_in("review_dial", DIALS), name="ck_autopilot_review_dial"),
        sa.CheckConstraint(
            ACTOR_CHECK.replace("actor", "updated_by"), name="ck_autopilot_updated_by"
        ),
    )
    op.create_table(
        "autopilot_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("account_id", sa.String(length=40), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("at", TS, nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("field", sa.Text(), nullable=False),
        sa.Column("from_value", sa.Text(), nullable=True),
        sa.Column("to_value", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.CheckConstraint(ACTOR_CHECK, name="ck_autopilot_events_actor"),
    )
    op.create_index("ix_autopilot_events_account", "autopilot_events", ["account_id", "at"])
    op.execute("""create function autopilot_events_append_only() returns trigger
                  language plpgsql as
                  $$ begin raise exception 'autopilot_events is append-only'; end $$""")
    op.execute("""create trigger autopilot_events_no_change
                  before update or delete on autopilot_events
                  for each row execute function autopilot_events_append_only()""")
    op.create_table(
        "slot_plans",
        sa.Column(
            "account_id", sa.String(length=40), sa.ForeignKey("accounts.id"), primary_key=True
        ),
        sa.Column("slot", TS, primary_key=True),
        sa.Column(
            "item_id", sa.String(length=64), sa.ForeignKey("content_items.id"), nullable=True
        ),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("planned_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.CheckConstraint(_in("state", PLAN_STATES), name="ck_slot_plans_state"),
    )
    op.create_table(
        "webhook_deliveries",
        sa.Column("delivery_id", sa.Text(), primary_key=True),
        sa.Column("event", sa.Text(), nullable=False),
        sa.Column("received_at", TS, nullable=False),
        sa.Column("payload", JSONB_, nullable=False),
        sa.Column("processed_at", TS, nullable=True),
    )
    op.create_table(
        "links",
        sa.Column("slug", sa.String(length=16), primary_key=True),
        sa.Column("target_url", sa.Text(), nullable=False),
        sa.Column("account_id", sa.String(length=40), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column(
            "item_id", sa.String(length=64), sa.ForeignKey("content_items.id"), nullable=True
        ),
        sa.Column("platform", sa.String(length=16), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("sub_param", sa.Text(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
    )
    op.create_table(
        "clicks",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("slug", sa.String(length=16), sa.ForeignKey("links.slug"), nullable=False),
        sa.Column("at", TS, nullable=False),
        sa.Column("platform", sa.String(length=16), nullable=True),
        sa.Column("sub_id", sa.Text(), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=True),
    )
    op.create_index("ix_clicks_slug_at", "clicks", ["slug", "at"])

    # ---- seed: one Hands-on row per existing account (spec §3, log #451); the cap from the
    # budget, else the type default (S3 dashboard spec §2.6)
    op.execute("""insert into autopilot (account_id, preset, produce, review_dial, publish, scale,
                    runway_days, batch_line_usd, monthly_cap_usd, updated_by, updated_at)
                  select id, 'hands_on', false, 'review', true, false, 7, 2.0,
                    case when monthly_budget_usd > 0 then monthly_budget_usd
                         else case kind when 'clips' then 5 when 'avatar' then 20 else 10 end
                    end,
                    'system:migration', now() from accounts""")
    op.execute("""insert into autopilot_events (account_id, at, actor, field, from_value,
                    to_value, reason)
                  select id, now(), 'system:migration', 'preset', null, 'hands_on',
                    'S2 migration seed' from accounts""")


def downgrade() -> None:
    op.execute("drop trigger autopilot_events_no_change on autopilot_events")
    op.execute("drop function autopilot_events_append_only()")
    op.drop_index("ix_clicks_slug_at", table_name="clicks")
    op.drop_table("clicks")
    op.drop_table("links")
    op.drop_table("webhook_deliveries")
    op.drop_table("slot_plans")
    op.drop_index("ix_autopilot_events_account", table_name="autopilot_events")
    op.drop_table("autopilot_events")
    op.drop_table("autopilot")
    op.drop_index("ix_posts_upload_job", table_name="posts")
    op.drop_index("ix_posts_state_scheduled", table_name="posts")
    op.drop_constraint("ck_posts_state", "posts")
    for name in ("attempts", "state", "copy", "error", "upload_job_id", "request_id",
                 "handed_off_at", "scheduled_for", "claimed_at", "publisher"):  # fmt: skip
        op.drop_column("posts", name)
    for name in ("approved_by", "approved_at", "gate", "review_window", "review_dial",
                 "review_reasons", "review_lane", "copy"):  # fmt: skip
        op.drop_column("content_items", name)
    op.drop_column("accounts", "publisher")
    op.drop_constraint("ck_posting_state_changed_by", "posting_state")
    op.drop_column("posting_state", "reason")
    op.drop_column("posting_state", "changed_by")
    op.drop_constraint("ck_post_events_actor", "post_events")
    op.drop_column("post_events", "actor")
    op.drop_column("jobs", "error")
