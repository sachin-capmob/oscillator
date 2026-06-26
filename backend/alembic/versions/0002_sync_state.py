"""sync_state watermark for the cron poller

Revision ID: 0002_sync_state
Revises: 0001_initial
Create Date: 2026-06-27
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0002_sync_state"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sync_state",
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("sync_state")
