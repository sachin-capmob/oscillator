"""anomalies + digests: statistical flags and cached narrative summaries

Two small tables written by the cron sync (after rollups refresh):

  * anomalies — one row per (entity, metric, period) whose observed value
    deviates from its trailing baseline by more than a z-score threshold.
    Recomputed each sync for the current period, so a natural key
    (scope, entity_id, metric, period) is UPSERTed to keep it idempotent.
  * digests   — one cached narrative per (range, anchor), regenerated each
    sync. The API reads these instead of calling the LLM per request, keeping
    the read path fast and the LLM cost bounded to ~8 calls/day.

Revision ID: 0004_anomalies_digests
Revises: 0003_materialized_views
Create Date: 2026-07-02
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0004_anomalies_digests"
down_revision = "0003_materialized_views"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "anomalies",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        # 'workspace' | 'team' | 'actor'
        sa.Column("scope", sa.String(16), nullable=False),
        # surrogate id of the team/actor; NULL for workspace-scoped rows
        sa.Column("entity_id", sa.BigInteger()),
        sa.Column("entity_name", sa.String(255)),
        # 'throughput' | 'cycle_time' | 'wip' | 'net_flow' | 'comments'
        sa.Column("metric", sa.String(32), nullable=False),
        # the period bucket start this anomaly was observed in
        sa.Column("period", sa.Date(), nullable=False),
        # 'up' | 'down' — direction of the deviation
        sa.Column("direction", sa.String(8), nullable=False),
        # 'info' | 'warn' | 'critical' — bucketed from |z|
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("observed", sa.Float(), nullable=False),
        sa.Column("baseline", sa.Float(), nullable=False),
        sa.Column("stddev", sa.Float()),
        sa.Column("z_score", sa.Float(), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        # Natural key so re-detecting the same period is an idempotent upsert.
        sa.UniqueConstraint("scope", "entity_id", "metric", "period", name="uq_anomaly_key"),
    )
    op.create_index("ix_anomalies_period", "anomalies", ["period"])
    op.create_index("ix_anomalies_severity", "anomalies", ["severity"])

    op.create_table(
        "digests",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("range", sa.String(8), nullable=False),
        sa.Column("anchor", sa.Date(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        # 'groq' | 'template' — how the summary was produced
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("model", sa.String(128)),
        sa.Column("anomaly_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("range", "anchor", name="uq_digest_key"),
    )
    op.create_index("ix_digests_generated_at", "digests", ["generated_at"])


def downgrade() -> None:
    op.drop_table("digests")
    op.drop_table("anomalies")
