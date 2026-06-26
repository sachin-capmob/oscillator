
"""materialized views: daily_actor_rollup, weekly_team_rollup, monthly_team_rollup

Each view has a UNIQUE index on its grain so the cron sync can
``REFRESH MATERIALIZED VIEW CONCURRENTLY``.

Metrics:
  * throughput        — issues completed in the period
  * avg/median cycle  — completed_at - started_at (hours), over issues with a started_at
  * comments          — comments authored in the period
  * wip (team views)  — issues in 'started' state at some point during the period
  * scope_added       — issues attached to a cycle and created after the cycle started

Revision ID: 0003_materialized_views
Revises: 0002_sync_state
Create Date: 2026-06-27
"""

from __future__ import annotations

from alembic import op

revision = "0003_materialized_views"
down_revision = "0002_sync_state"
branch_labels = None
depends_on = None


DAILY_ACTOR = """
CREATE MATERIALIZED VIEW daily_actor_rollup AS
WITH completed AS (
  SELECT assignee_id AS actor_id,
         date_trunc('day', completed_at)::date AS day,
         count(*) AS throughput,
         avg(extract(epoch FROM completed_at - started_at) / 3600.0)
           FILTER (WHERE started_at IS NOT NULL) AS avg_cycle_hours,
         percentile_cont(0.5) WITHIN GROUP (
           ORDER BY extract(epoch FROM completed_at - started_at) / 3600.0)
           FILTER (WHERE started_at IS NOT NULL) AS median_cycle_hours
  FROM issues
  WHERE completed_at IS NOT NULL AND assignee_id IS NOT NULL
  GROUP BY 1, 2
),
commented AS (
  SELECT actor_id, date_trunc('day', created_at)::date AS day, count(*) AS comments
  FROM comments
  WHERE created_at IS NOT NULL AND actor_id IS NOT NULL
  GROUP BY 1, 2
)
SELECT
  COALESCE(c.actor_id, m.actor_id) AS actor_id,
  COALESCE(c.day, m.day) AS day,
  COALESCE(c.throughput, 0) AS throughput,
  c.avg_cycle_hours,
  c.median_cycle_hours,
  COALESCE(m.comments, 0) AS comments
FROM completed c
FULL OUTER JOIN commented m ON c.actor_id = m.actor_id AND c.day = m.day;
"""


def _team_rollup(view: str, unit: str, period_col: str) -> str:
    """Build a weekly/monthly team rollup view definition."""
    return f"""
CREATE MATERIALIZED VIEW {view} AS
WITH bounds AS (
  SELECT date_trunc('{unit}', COALESCE(min(created_at), now())) AS first_period FROM issues
),
periods AS (
  SELECT gs AS period_start
  FROM bounds,
       generate_series(bounds.first_period, date_trunc('{unit}', now()), interval '1 {unit}') AS gs
),
team_periods AS (
  SELECT t.id AS team_id, p.period_start,
         (p.period_start + interval '1 {unit}') AS period_end
  FROM teams t CROSS JOIN periods p
),
throughput AS (
  SELECT team_id, date_trunc('{unit}', completed_at) AS p,
         count(*) AS throughput,
         avg(extract(epoch FROM completed_at - started_at) / 3600.0)
           FILTER (WHERE started_at IS NOT NULL) AS avg_cycle_hours,
         percentile_cont(0.5) WITHIN GROUP (
           ORDER BY extract(epoch FROM completed_at - started_at) / 3600.0)
           FILTER (WHERE started_at IS NOT NULL) AS median_cycle_hours
  FROM issues
  WHERE completed_at IS NOT NULL AND team_id IS NOT NULL
  GROUP BY 1, 2
),
commented AS (
  SELECT i.team_id, date_trunc('{unit}', c.created_at) AS p, count(*) AS comments
  FROM comments c JOIN issues i ON i.id = c.issue_id
  WHERE c.created_at IS NOT NULL AND i.team_id IS NOT NULL
  GROUP BY 1, 2
),
scope AS (
  SELECT i.team_id, date_trunc('{unit}', i.created_at) AS p, count(*) AS scope_added
  FROM issues i JOIN cycles cy ON cy.id = i.cycle_id
  WHERE cy.starts_at IS NOT NULL AND i.created_at > cy.starts_at AND i.team_id IS NOT NULL
  GROUP BY 1, 2
)
SELECT
  tp.team_id,
  tp.period_start::date AS {period_col},
  COALESCE(thr.throughput, 0) AS throughput,
  thr.avg_cycle_hours,
  thr.median_cycle_hours,
  COALESCE(cm.comments, 0) AS comments,
  COALESCE(sc.scope_added, 0) AS scope_added,
  (SELECT count(*) FROM issues i
     WHERE i.team_id = tp.team_id
       AND i.started_at IS NOT NULL
       AND i.started_at < tp.period_end
       AND (i.completed_at IS NULL OR i.completed_at >= tp.period_start)
       AND (i.canceled_at IS NULL OR i.canceled_at >= tp.period_start)
  ) AS wip
FROM team_periods tp
LEFT JOIN throughput thr ON thr.team_id = tp.team_id AND thr.p = tp.period_start
LEFT JOIN commented cm ON cm.team_id = tp.team_id AND cm.p = tp.period_start
LEFT JOIN scope sc ON sc.team_id = tp.team_id AND sc.p = tp.period_start;
"""


def upgrade() -> None:
    op.execute(DAILY_ACTOR)
    op.execute("CREATE UNIQUE INDEX ux_daily_actor_rollup ON daily_actor_rollup (actor_id, day)")

    op.execute(_team_rollup("weekly_team_rollup", "week", "week_start"))
    op.execute(
        "CREATE UNIQUE INDEX ux_weekly_team_rollup ON weekly_team_rollup (team_id, week_start)"
    )

    op.execute(_team_rollup("monthly_team_rollup", "month", "month_start"))
    op.execute(
        "CREATE UNIQUE INDEX ux_monthly_team_rollup ON monthly_team_rollup (team_id, month_start)"
    )


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS monthly_team_rollup")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS weekly_team_rollup")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS daily_actor_rollup")
