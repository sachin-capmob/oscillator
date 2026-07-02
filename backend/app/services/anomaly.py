"""Deterministic anomaly detection over the materialized rollups.

No LLM here — pure statistics, safe to run every sync. For each metric series
(workspace-wide, per-team, per-actor) we take the trailing baseline (the
periods *before* the most recent one), compute mean + population stddev, and
flag the most recent period when it deviates by more than a z-score threshold.

The most recent complete-ish period is the detection target; older periods form
the baseline. We require a minimum number of baseline periods with signal so a
brand-new workspace doesn't light up with noise.

Results are UPSERTed on (scope, entity_id, metric, period) so re-running a sync
never duplicates a flag — it just refreshes the numbers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Anomaly

logger = logging.getLogger("app.anomaly")

# Detection knobs.
MIN_BASELINE = 4          # need at least this many prior periods to judge
Z_WARN = 2.0              # |z| >= this → warn
Z_CRITICAL = 3.0          # |z| >= this → critical
MIN_ABS_CHANGE = 2.0      # ignore tiny absolute moves (counts) below this
WEEKS_LOOKBACK = 12       # how many weekly buckets to pull for baselines


@dataclass
class Series:
    """A metric time series for one entity, oldest→newest."""

    scope: str
    metric: str
    entity_id: int | None
    entity_name: str | None
    # (period, value) oldest first; the last element is the detection target.
    points: list[tuple[date, float]]


def _evaluate(s: Series) -> dict | None:
    """Return an anomaly row dict for the latest point, or None if unremarkable."""
    if len(s.points) < MIN_BASELINE + 1:
        return None
    *baseline_pts, (period, observed) = s.points
    values = [v for _, v in baseline_pts]
    n = len(values)
    if n < MIN_BASELINE:
        return None
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / n  # population variance
    stddev = var ** 0.5

    if stddev == 0:
        # Flat baseline: only flag a departure that also clears the abs floor.
        if abs(observed - mean) < MIN_ABS_CHANGE:
            return None
        z = float("inf") if observed != mean else 0.0
    else:
        z = (observed - mean) / stddev

    if abs(z) < Z_WARN or abs(observed - mean) < MIN_ABS_CHANGE:
        return None

    direction = "up" if observed >= mean else "down"
    severity = "critical" if abs(z) >= Z_CRITICAL else "warn"
    # Cap infinities so they store/serialize cleanly.
    z_stored = round(max(-99.0, min(99.0, z)), 2)

    return {
        "scope": s.scope,
        "entity_id": s.entity_id,
        "entity_name": s.entity_name,
        "metric": s.metric,
        "period": period,
        "direction": direction,
        "severity": severity,
        "observed": round(observed, 2),
        "baseline": round(mean, 2),
        "stddev": round(stddev, 2),
        "z_score": z_stored,
    }


async def _workspace_series(session: AsyncSession) -> list[Series]:
    """Workspace-wide weekly throughput, created, and net-flow series."""
    # WEEKS_LOOKBACK is a module constant (never user input); Postgres cannot bind
    # a parameter inside an `interval` literal, so we interpolate it directly —
    # the same whitelisted-fragment pattern the trend queries use.
    rows = (
        await session.execute(
            text(
                f"""
                WITH spine AS (
                  SELECT gs::date AS period
                  FROM generate_series(
                    date_trunc('week', now()) - interval '{WEEKS_LOOKBACK} weeks',
                    date_trunc('week', now()),
                    interval '1 week'
                  ) gs
                )
                SELECT s.period,
                  COALESCE(c.value, 0)::float AS completed,
                  COALESCE(cr.value, 0)::float AS created
                FROM spine s
                LEFT JOIN (
                  SELECT date_trunc('week', completed_at)::date AS period, count(*) AS value
                  FROM issues WHERE completed_at IS NOT NULL GROUP BY 1
                ) c ON c.period = s.period
                LEFT JOIN (
                  SELECT date_trunc('week', created_at)::date AS period, count(*) AS value
                  FROM issues WHERE created_at IS NOT NULL GROUP BY 1
                ) cr ON cr.period = s.period
                ORDER BY s.period
                """
            ),
        )
    ).mappings().all()
    if not rows:
        return []
    completed = [(r["period"], r["completed"]) for r in rows]
    created = [(r["period"], r["created"]) for r in rows]
    net = [(r["period"], r["created"] - r["completed"]) for r in rows]
    return [
        Series("workspace", "throughput", None, "Workspace", completed),
        Series("workspace", "created", None, "Workspace", created),
        Series("workspace", "net_flow", None, "Workspace", net),
    ]


async def _team_series(session: AsyncSession) -> list[Series]:
    """Per-team weekly throughput, cycle time, and WIP from the weekly rollup."""
    rows = (
        await session.execute(
            text(
                f"""
                SELECT r.team_id, t.name, r.week_start AS period,
                       r.throughput::float AS throughput,
                       r.avg_cycle_hours, r.wip::float AS wip
                FROM weekly_team_rollup r
                JOIN teams t ON t.id = r.team_id
                WHERE r.week_start >= (
                  date_trunc('week', now()) - interval '{WEEKS_LOOKBACK} weeks'
                )::date
                ORDER BY r.team_id, r.week_start
                """
            ),
        )
    ).mappings().all()

    by_team: dict[int, dict] = {}
    for r in rows:
        t = by_team.setdefault(r["team_id"], {"name": r["name"], "thr": [], "cyc": [], "wip": []})
        t["thr"].append((r["period"], r["throughput"]))
        if r["avg_cycle_hours"] is not None:
            t["cyc"].append((r["period"], float(r["avg_cycle_hours"])))
        t["wip"].append((r["period"], r["wip"]))

    out: list[Series] = []
    for team_id, t in by_team.items():
        out.append(Series("team", "throughput", team_id, t["name"], t["thr"]))
        out.append(Series("team", "cycle_time", team_id, t["name"], t["cyc"]))
        out.append(Series("team", "wip", team_id, t["name"], t["wip"]))
    return out


async def detect_anomalies(session: AsyncSession) -> int:
    """Compute and UPSERT anomalies for the latest period. Returns rows written."""
    series = (await _workspace_series(session)) + (await _team_series(session))
    detected = [row for s in series if (row := _evaluate(s)) is not None]

    if not detected:
        logger.info("Anomaly detection: no flags")
        return 0

    stmt = pg_insert(Anomaly).values(detected)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_anomaly_key",
        set_={
            "entity_name": stmt.excluded.entity_name,
            "direction": stmt.excluded.direction,
            "severity": stmt.excluded.severity,
            "observed": stmt.excluded.observed,
            "baseline": stmt.excluded.baseline,
            "stddev": stmt.excluded.stddev,
            "z_score": stmt.excluded.z_score,
            "detected_at": text("now()"),
        },
    )
    await session.execute(stmt)
    logger.info("Anomaly detection: %d flags", len(detected))
    return len(detected)
