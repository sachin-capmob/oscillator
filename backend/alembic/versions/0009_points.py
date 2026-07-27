"""engineering points ledger: points_events, points_unscored_tickets

points_events is append-only (see app/models/points.py docstring) — a
`reverted`/`rca-done` tag produces a NEW row, never an UPDATE of the
original award, so history as of any past date stays correct. Partial-unique
indexes (not plain UniqueConstraints, since they need a WHERE clause) enforce
idempotency: one `award` per (issue, category), one `reversal` per reversed
award, one `bonus` per bonused award.

points_unscored_tickets is a plain upsert-by-issue_id table (natural key =
issue_id), same shape as the existing `anomalies` upsert-by-natural-key
pattern from 0004.

Revision ID: 0009_points
Revises: 0008_zoho_issue_columns
Create Date: 2026-07-27
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0009_points"
down_revision = "0008_zoho_issue_columns"
branch_labels = None
depends_on = None


def _ts(timezone: bool = True) -> sa.DateTime:
    return sa.DateTime(timezone=timezone)


def upgrade() -> None:
    op.create_table(
        "points_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("issue_id", sa.BigInteger(), nullable=False),
        sa.Column("actor_id", sa.BigInteger()),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("event_kind", sa.String(16), server_default="award", nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("rule_key", sa.String(128)),
        sa.Column("rules_version", sa.String(32)),
        sa.Column("label_state", postgresql.JSONB()),
        sa.Column("source_tag_event_id", sa.BigInteger()),
        sa.Column("reverses_event_id", sa.BigInteger()),
        sa.Column("related_event_id", sa.BigInteger()),
        sa.Column("effective_at", _ts(), nullable=False),
        sa.Column("awarded_at", _ts(), server_default=sa.text("now()"), nullable=False),
        sa.Column("ingested_at", _ts(), server_default=sa.text("now()"), nullable=False),
        sa.Column("row_updated_at", _ts(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["issue_id"], ["issues.id"], ondelete="CASCADE", name="fk_points_events_issue_id"
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["actors.id"], ondelete="SET NULL", name="fk_points_events_actor_id"
        ),
        sa.ForeignKeyConstraint(
            ["reverses_event_id"], ["points_events.id"], ondelete="SET NULL",
            name="fk_points_events_reverses_event_id",
        ),
        sa.ForeignKeyConstraint(
            ["related_event_id"], ["points_events.id"], ondelete="SET NULL",
            name="fk_points_events_related_event_id",
        ),
    )
    op.create_index("ix_points_events_issue_id", "points_events", ["issue_id"])
    op.create_index("ix_points_events_actor_id", "points_events", ["actor_id"])
    op.create_index("ix_points_events_category", "points_events", ["category"])
    op.create_index("ix_points_events_effective_at", "points_events", ["effective_at"])
    op.create_index(
        "uq_points_events_award_per_category",
        "points_events",
        ["issue_id", "category"],
        unique=True,
        postgresql_where=sa.text("event_kind = 'award'"),
    )
    op.create_index(
        "uq_points_events_reverses_once",
        "points_events",
        ["reverses_event_id"],
        unique=True,
        postgresql_where=sa.text("event_kind = 'reversal'"),
    )
    op.create_index(
        "uq_points_events_bonus_once",
        "points_events",
        ["related_event_id"],
        unique=True,
        postgresql_where=sa.text("event_kind = 'bonus'"),
    )

    op.create_table(
        "points_unscored_tickets",
        sa.Column("issue_id", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("assignee_id", sa.BigInteger()),
        sa.Column("first_detected_at", _ts(), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_checked_at", _ts(), server_default=sa.text("now()"), nullable=False),
        sa.Column("notified_at", _ts()),
        sa.Column("resolved_at", _ts()),
        sa.PrimaryKeyConstraint("issue_id"),
        sa.ForeignKeyConstraint(
            ["issue_id"], ["issues.id"], ondelete="CASCADE",
            name="fk_points_unscored_tickets_issue_id",
        ),
        sa.ForeignKeyConstraint(
            ["assignee_id"], ["actors.id"], ondelete="SET NULL",
            name="fk_points_unscored_tickets_assignee_id",
        ),
    )
    op.create_index(
        "ix_points_unscored_assignee_id", "points_unscored_tickets", ["assignee_id"]
    )


def downgrade() -> None:
    op.drop_table("points_unscored_tickets")
    op.drop_table("points_events")
