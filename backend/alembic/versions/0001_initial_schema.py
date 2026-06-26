"""initial schema: core dimensions, issues + history, comments, raw_events

Partitioned tables (raw_events BY received_at, issue_history BY changed_at) are
created here WITHOUT child partitions — these are added at runtime by
app.db_partitions (ensure-before-insert), keeping this migration deterministic.

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-27
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def _ts(timezone: bool = True) -> sa.DateTime:
    return sa.DateTime(timezone=timezone)


def upgrade() -> None:
    # --- teams ---
    op.create_table(
        "teams",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("linear_id", sa.String(64), nullable=False),
        sa.Column("key", sa.String(32)),
        sa.Column("name", sa.String(255)),
        sa.Column("archived_at", _ts()),
        sa.Column("ingested_at", _ts(), server_default=sa.text("now()"), nullable=False),
        sa.Column("row_updated_at", _ts(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("linear_id", name="uq_teams_linear_id"),
    )

    # --- actors ---
    op.create_table(
        "actors",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("linear_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255)),
        sa.Column("email", sa.String(320)),
        sa.Column("avatar_url", sa.String(1024)),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("ingested_at", _ts(), server_default=sa.text("now()"), nullable=False),
        sa.Column("row_updated_at", _ts(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("linear_id", name="uq_actors_linear_id"),
    )
    op.create_index("ix_actors_email", "actors", ["email"])

    # --- cycles ---
    op.create_table(
        "cycles",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("linear_id", sa.String(64), nullable=False),
        sa.Column("team_id", sa.BigInteger()),
        sa.Column("number", sa.Integer()),
        sa.Column("name", sa.String(255)),
        sa.Column("starts_at", _ts()),
        sa.Column("ends_at", _ts()),
        sa.Column("completed_at", _ts()),
        sa.Column("ingested_at", _ts(), server_default=sa.text("now()"), nullable=False),
        sa.Column("row_updated_at", _ts(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("linear_id", name="uq_cycles_linear_id"),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], ondelete="CASCADE", name="fk_cycles_team_id"
        ),
    )
    op.create_index("ix_cycles_team_id", "cycles", ["team_id"])

    # --- issues ---
    op.create_table(
        "issues",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("linear_id", sa.String(64), nullable=False),
        sa.Column("identifier", sa.String(64)),
        sa.Column("title", sa.Text()),
        sa.Column("team_id", sa.BigInteger()),
        sa.Column("assignee_id", sa.BigInteger()),
        sa.Column("creator_id", sa.BigInteger()),
        sa.Column("cycle_id", sa.BigInteger()),
        sa.Column("state", sa.String(128)),
        sa.Column("state_type", sa.String(32)),
        sa.Column("priority", sa.Integer()),
        sa.Column("estimate", sa.Float()),
        sa.Column("project_id", sa.String(64)),
        sa.Column("created_at", _ts()),
        sa.Column("started_at", _ts()),
        sa.Column("completed_at", _ts()),
        sa.Column("canceled_at", _ts()),
        sa.Column("updated_at", _ts()),
        sa.Column("ingested_at", _ts(), server_default=sa.text("now()"), nullable=False),
        sa.Column("row_updated_at", _ts(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("linear_id", name="uq_issues_linear_id"),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], ondelete="SET NULL", name="fk_issues_team_id"
        ),
        sa.ForeignKeyConstraint(
            ["assignee_id"], ["actors.id"], ondelete="SET NULL", name="fk_issues_assignee_id"
        ),
        sa.ForeignKeyConstraint(
            ["creator_id"], ["actors.id"], ondelete="SET NULL", name="fk_issues_creator_id"
        ),
        sa.ForeignKeyConstraint(
            ["cycle_id"], ["cycles.id"], ondelete="SET NULL", name="fk_issues_cycle_id"
        ),
    )
    op.create_index("ix_issues_assignee_id", "issues", ["assignee_id"])
    op.create_index("ix_issues_team_id", "issues", ["team_id"])
    op.create_index("ix_issues_state_type", "issues", ["state_type"])
    op.create_index("ix_issues_completed_at", "issues", ["completed_at"])
    op.create_index("ix_issues_cycle_id", "issues", ["cycle_id"])
    op.create_index("ix_issues_updated_at", "issues", ["updated_at"])

    # --- comments ---
    op.create_table(
        "comments",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("linear_id", sa.String(64), nullable=False),
        sa.Column("issue_id", sa.BigInteger(), nullable=False),
        sa.Column("actor_id", sa.BigInteger()),
        sa.Column("body", sa.Text()),
        sa.Column("created_at", _ts()),
        sa.Column("ingested_at", _ts(), server_default=sa.text("now()"), nullable=False),
        sa.Column("row_updated_at", _ts(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("linear_id", name="uq_comments_linear_id"),
        sa.ForeignKeyConstraint(
            ["issue_id"], ["issues.id"], ondelete="CASCADE", name="fk_comments_issue_id"
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["actors.id"], ondelete="SET NULL", name="fk_comments_actor_id"
        ),
    )
    op.create_index("ix_comments_actor_id", "comments", ["actor_id"])
    op.create_index("ix_comments_issue_id", "comments", ["issue_id"])
    op.create_index("ix_comments_created_at", "comments", ["created_at"])

    # --- issue_history (PARTITION BY RANGE (changed_at)) ---
    op.create_table(
        "issue_history",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("changed_at", _ts(), nullable=False),
        sa.Column("linear_id", sa.String(64)),
        sa.Column("issue_id", sa.BigInteger(), nullable=False),
        sa.Column("actor_id", sa.BigInteger()),
        sa.Column("from_state", sa.String(128)),
        sa.Column("to_state", sa.String(128)),
        sa.Column("from_state_type", sa.String(32)),
        sa.Column("to_state_type", sa.String(32)),
        sa.PrimaryKeyConstraint("id", "changed_at"),
        sa.UniqueConstraint("linear_id", "changed_at", name="uq_issue_history_node"),
        sa.ForeignKeyConstraint(
            ["issue_id"], ["issues.id"], ondelete="CASCADE", name="fk_issue_history_issue_id"
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["actors.id"], ondelete="SET NULL", name="fk_issue_history_actor_id"
        ),
        postgresql_partition_by="RANGE (changed_at)",
    )
    op.create_index("ix_issue_history_issue_id", "issue_history", ["issue_id"])
    op.create_index("ix_issue_history_changed_at", "issue_history", ["changed_at"])

    # --- raw_events (PARTITION BY RANGE (received_at)) ---
    op.create_table(
        "raw_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("received_at", _ts(), server_default=sa.text("now()"), nullable=False),
        sa.Column("source", sa.String(32), server_default=sa.text("'linear'"), nullable=False),
        sa.Column("event_type", sa.String(128)),
        sa.Column("action", sa.String(64)),
        sa.Column("delivery_id", sa.String(128)),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("processed_at", _ts()),
        sa.PrimaryKeyConstraint("id", "received_at"),
        postgresql_partition_by="RANGE (received_at)",
    )
    op.create_index("ix_raw_events_event_type", "raw_events", ["event_type"])
    op.create_index("ix_raw_events_received_at", "raw_events", ["received_at"])
    op.create_index(
        "ix_raw_events_unprocessed",
        "raw_events",
        ["received_at"],
        postgresql_where=sa.text("processed_at IS NULL"),
    )


def downgrade() -> None:
    # Dropping a partitioned parent cascades to its child partitions.
    op.drop_table("raw_events")
    op.drop_table("issue_history")
    op.drop_table("comments")
    op.drop_table("issues")
    op.drop_table("cycles")
    op.drop_index("ix_actors_email", table_name="actors")
    op.drop_table("actors")
    op.drop_table("teams")
