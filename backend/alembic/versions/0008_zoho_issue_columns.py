"""zoho issue columns: zoho_id everywhere, plus issue-specific Zoho fields

Adds a `zoho_id` column (nullable, unique) to teams/actors/cycles/issues/
comments alongside the existing `linear_id`, and relaxes `linear_id` to
nullable on all five — a row synced from Zoho Sprints carries `zoho_id`
instead of `linear_id`, never both. `creator_id`/`estimate` on `issues` are
REUSED for Zoho's `createdBy`/`points` (same "reporter"/"size estimate"
semantics as Linear's creator/estimate) rather than adding parallel columns.

Also adds `issues.completed_by_id` (no Linear equivalent — who actually
marked it done, which can differ from assignee_id), `issues.epic_id` /
`issues.zoho_project_id` (Zoho's item hierarchy), and `issues.priority_label`
(Zoho's priority is a project-scoped custom enum, not Linear's fixed 0-4 int,
so it's stored as the raw label rather than forced into the existing
`priority` int column). Extends the `issues.source` value set with
'zoho_sprints' (no schema change needed — same free-text column 0006 added
for 'custom').

Revision ID: 0008_zoho_issue_columns
Revises: 0007_zoho_dimensions
Create Date: 2026-07-27
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0008_zoho_issue_columns"
down_revision = "0007_zoho_dimensions"
branch_labels = None
depends_on = None

# (table, unique-constraint-name-to-drop-and-recreate) — linear_id is unique
# NOT NULL today; Postgres allows multiple NULLs under a plain UNIQUE
# constraint, so relaxing nullability needs no index change, only the
# NOT NULL flag itself.
_TABLES_WITH_LINEAR_ID = ["teams", "actors", "cycles", "issues", "comments"]


def upgrade() -> None:
    for table in _TABLES_WITH_LINEAR_ID:
        op.alter_column(table, "linear_id", existing_type=sa.String(64), nullable=True)
        op.add_column(table, sa.Column("zoho_id", sa.String(64)))
        op.create_unique_constraint(f"uq_{table}_zoho_id", table, ["zoho_id"])

    op.add_column("issues", sa.Column("completed_by_id", sa.BigInteger()))
    op.add_column("issues", sa.Column("epic_id", sa.BigInteger()))
    op.add_column("issues", sa.Column("zoho_project_id", sa.BigInteger()))
    op.add_column("issues", sa.Column("priority_label", sa.String(64)))

    op.create_foreign_key(
        "fk_issues_completed_by_id", "issues", "actors", ["completed_by_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_issues_epic_id", "issues", "epics", ["epic_id"], ["id"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_issues_zoho_project_id", "issues", "projects", ["zoho_project_id"], ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_issues_zoho_project_id", "issues", type_="foreignkey")
    op.drop_constraint("fk_issues_epic_id", "issues", type_="foreignkey")
    op.drop_constraint("fk_issues_completed_by_id", "issues", type_="foreignkey")

    op.drop_column("issues", "priority_label")
    op.drop_column("issues", "zoho_project_id")
    op.drop_column("issues", "epic_id")
    op.drop_column("issues", "completed_by_id")

    for table in _TABLES_WITH_LINEAR_ID:
        op.drop_constraint(f"uq_{table}_zoho_id", table, type_="unique")
        op.drop_column(table, "zoho_id")
        op.alter_column(table, "linear_id", existing_type=sa.String(64), nullable=False)
