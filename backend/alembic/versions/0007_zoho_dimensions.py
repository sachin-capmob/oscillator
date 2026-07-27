"""zoho dimensions: projects, epics, tags, issue tag associations, status defs

Additive only — no existing table is touched. Safe to ship and sit ahead of
the Zoho Sprints client/normalizer/sync-job code landing (0008 follows with
the new columns on teams/actors/cycles/issues/comments).

issue_tags holds the CURRENT tag set per issue (removed_at IS NULL = still
attached). issue_tag_history is the append-only diff log — same
PARTITION BY RANGE (changed_at) shape as issue_history, created here with NO
child partitions (created at runtime by app.db_partitions, same as every
other partitioned table).

Revision ID: 0007_zoho_dimensions
Revises: 0006_custom_issues
Create Date: 2026-07-27
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0007_zoho_dimensions"
down_revision = "0006_custom_issues"
branch_labels = None
depends_on = None


def _ts(timezone: bool = True) -> sa.DateTime:
    return sa.DateTime(timezone=timezone)


def upgrade() -> None:
    # --- projects (Zoho: team -> project -> sprint/epic -> item) ---
    op.create_table(
        "projects",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("zoho_id", sa.String(64), nullable=False),
        sa.Column("team_id", sa.BigInteger()),
        sa.Column("key", sa.String(32)),
        sa.Column("name", sa.String(255)),
        sa.Column("archived_at", _ts()),
        sa.Column("ingested_at", _ts(), server_default=sa.text("now()"), nullable=False),
        sa.Column("row_updated_at", _ts(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("zoho_id", name="uq_projects_zoho_id"),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], ondelete="SET NULL", name="fk_projects_team_id"
        ),
    )
    op.create_index("ix_projects_team_id", "projects", ["team_id"])

    # --- epics ---
    op.create_table(
        "epics",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("zoho_id", sa.String(64), nullable=False),
        sa.Column("project_id", sa.BigInteger()),
        sa.Column("name", sa.String(255)),
        sa.Column("ingested_at", _ts(), server_default=sa.text("now()"), nullable=False),
        sa.Column("row_updated_at", _ts(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("zoho_id", name="uq_epics_zoho_id"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="CASCADE", name="fk_epics_project_id"
        ),
    )
    op.create_index("ix_epics_project_id", "epics", ["project_id"])

    # --- tags (the dimension the Engineering Points system reads) ---
    op.create_table(
        "tags",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("zoho_id", sa.String(64), nullable=False),
        sa.Column("team_id", sa.BigInteger()),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("color_code", sa.String(16)),
        sa.Column("created_by_id", sa.BigInteger()),
        sa.Column("ingested_at", _ts(), server_default=sa.text("now()"), nullable=False),
        sa.Column("row_updated_at", _ts(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("zoho_id", name="uq_tags_zoho_id"),
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

    # --- status_defs (per-project Zoho status -> our state_type mapping) ---
    op.create_table(
        "status_defs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("zoho_status_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128)),
        sa.Column("state_type", sa.String(32), nullable=False),
        sa.Column("ingested_at", _ts(), server_default=sa.text("now()"), nullable=False),
        sa.Column("row_updated_at", _ts(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "zoho_status_id", name="uq_status_defs_project_status"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="CASCADE", name="fk_status_defs_project_id"
        ),
    )


def downgrade() -> None:
    op.drop_table("status_defs")
    op.drop_table("issue_tag_history")
    op.drop_table("issue_tags")
    op.drop_index("ix_tags_name", table_name="tags")
    op.drop_table("tags")
    op.drop_table("epics")
    op.drop_table("projects")
