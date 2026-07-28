"""labels + Engineering Points ledger

Adds the tag dimension the Engineering Points system reads (Linear issue
labels — type:*/sev:*/area:*/size:* and the triaged/reverted/rca-done
modifiers, already created in Linear per the team's scoring doc) plus the
append-only points ledger those tags feed.

- tags: one row per Linear label (linear_id keyed, same convention as every
  other dimension table).
- issue_tags: CURRENT tag set per issue (removed_at IS NULL = still attached).
- issue_tag_history: append-only add/remove diff log, PARTITION BY RANGE
  (changed_at) like issue_history — created here with NO child partitions
  (app.db_partitions creates them at runtime, same as every other
  partitioned table).
- points_events: the ledger. Partial-unique indexes (not plain
  UniqueConstraints, since they need a WHERE clause) enforce idempotency —
  one `award` per (issue, category), one `reversal` per reversed award, one
  `bonus` per bonused award.
- points_unscored_tickets: upsert-by-issue_id queue of tickets the scoring
  job couldn't resolve (missing/ambiguous labels, awaiting triage/close,
  needs manual review).

Revision ID: 0007_labels_and_points
Revises: 0006_custom_issues
Create Date: 2026-07-28
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0007_labels_and_points"
down_revision = "0006_custom_issues"
branch_labels = None
depends_on = None


def _ts(timezone: bool = True) -> sa.DateTime:
    return sa.DateTime(timezone=timezone)


def upgrade() -> None:
    # --- tags (the dimension the Engineering Points system reads) ---
    op.create_table(
        "tags",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("linear_id", sa.String(64), nullable=False),
        sa.Column("team_id", sa.BigInteger()),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("color_code", sa.String(16)),
        sa.Column("created_by_id", sa.BigInteger()),
        sa.Column("ingested_at", _ts(), server_default=sa.text("now()"), nullable=False),
        sa.Column("row_updated_at", _ts(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("linear_id", name="uq_tags_linear_id"),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], ondelete="CASCADE", name="fk_tags_team_id"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["actors.id"], ondelete="SET NULL", name="fk_tags_created_by_id"
        ),
    )
    op.create_index("ix_tags_name", "tags", ["name"])

    # --- issue_tags (current-state join) ---
    op.create_table(
        "issue_tags",
        sa.Column("issue_id", sa.BigInteger(), nullable=False),
        sa.Column("tag_id", sa.BigInteger(), nullable=False),
        sa.Column("added_at", _ts()),
        sa.Column("removed_at", _ts()),
        sa.PrimaryKeyConstraint("issue_id", "tag_id"),
        sa.ForeignKeyConstraint(
            ["issue_id"], ["issues.id"], ondelete="CASCADE", name="fk_issue_tags_issue_id"
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"], ["tags.id"], ondelete="CASCADE", name="fk_issue_tags_tag_id"
        ),
    )
    op.create_index("ix_issue_tags_issue_id", "issue_tags", ["issue_id"])
    op.create_index("ix_issue_tags_tag_id", "issue_tags", ["tag_id"])

    # --- issue_tag_history (PARTITION BY RANGE (changed_at), no child partitions here) ---
    op.create_table(
        "issue_tag_history",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("changed_at", _ts(), nullable=False),
        sa.Column("issue_id", sa.BigInteger(), nullable=False),
        sa.Column("tag_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),  # 'added' | 'removed'
        sa.PrimaryKeyConstraint("id", "changed_at"),
        sa.ForeignKeyConstraint(
            ["issue_id"], ["issues.id"], ondelete="CASCADE", name="fk_issue_tag_history_issue_id"
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"], ["tags.id"], ondelete="CASCADE", name="fk_issue_tag_history_tag_id"
        ),
        postgresql_partition_by="RANGE (changed_at)",
    )
    op.create_index("ix_issue_tag_history_issue_id", "issue_tag_history", ["issue_id"])
    op.create_index("ix_issue_tag_history_tag_id", "issue_tag_history", ["tag_id"])
    op.create_index("ix_issue_tag_history_changed_at", "issue_tag_history", ["changed_at"])

    # --- points_events (the ledger) ---
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

    # --- points_unscored_tickets ---
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
    op.drop_table("issue_tag_history")
    op.drop_table("issue_tags")
    op.drop_index("ix_tags_name", table_name="tags")
    op.drop_table("tags")
