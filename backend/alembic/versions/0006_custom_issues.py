"""custom issues: track non-Linear work items in the same issues table

Adds a `source` column ('linear' | 'custom') to `issues` so manually-created
work items (e.g. "set up AWS") flow through every existing insights query
(overview KPIs, throughput, by-actor, by-team) exactly like synced Linear
issues — no separate aggregation path to keep in sync.

Also drops `time_entries` — the manual clock-in/out feature is replaced by
custom issue tracking.

Revision ID: 0006_custom_issues
Revises: 0005_time_entries
Create Date: 2026-07-14
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0006_custom_issues"
down_revision = "0005_time_entries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("time_entries")

    op.add_column(
        "issues",
        sa.Column(
            "source",
            sa.String(length=16),
            nullable=False,
            server_default="linear",
        ),
    )
    op.create_index("ix_issues_source", "issues", ["source"])


def downgrade() -> None:
    op.drop_index("ix_issues_source", table_name="issues")
    op.drop_column("issues", "source")

    op.create_table(
        "time_entries",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("actor_id", sa.BigInteger(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["actors.id"],
            name="fk_time_entries_actor_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_time_entries_actor_id", "time_entries", ["actor_id"])
    op.create_index("ix_time_entries_started_at", "time_entries", ["started_at"])
    op.create_index("ix_time_entries_stopped_at", "time_entries", ["stopped_at"])
