"""time_entries: manual clock-in / clock-out tracking

Each row represents one work session for a team member. A NULL stopped_at
means the timer is still running. Only one active timer per actor is allowed.

Revision ID: 0005_time_entries
Revises: 0004_anomalies_digests
Create Date: 2026-07-12
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0005_time_entries"
down_revision = "0004_anomalies_digests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "time_entries",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        # FK to the actors table (Linear team members).
        # ON DELETE SET NULL so deleting an actor doesn't destroy history.
        sa.Column("actor_id", sa.BigInteger(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        # NULL while the timer is running; set on /stop.
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        # Optional free-text note added at stop time (or start).
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


def downgrade() -> None:
    op.drop_table("time_entries")
