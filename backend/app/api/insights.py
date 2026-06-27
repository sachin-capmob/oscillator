"""Read-only insights API. All endpoints require a bearer token (see deps.py).

Trends (throughput / cycle-time / wip) are computed from the base `issues` table
grouped by period; per-entity breakdowns (by-actor / by-team) read the
materialized rollups. Range selects the period granularity + window.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_token
from app.db import get_session
from app.schemas.insights import (
    ActorStat,
    ActorThroughputPoint,
    ActorThroughputStat,
    ByActorResponse,
    ByTeamResponse,
    CycleTimePoint,
    CycleTimeResponse,
    DualPoint,
    Metric,
    OverviewResponse,
    Range,
    TeamStat,
    ThroughputByActorResponse,
    ThroughputResponse,
    TimeseriesPoint,
    WipResponse,
)

router = APIRouter(prefix="/api/insights", tags=["insights"], dependencies=[Depends(require_token)])

# Whitelisted SQL fragments per range (never interpolate user input directly).
TREND = {
    Range.day: {"unit": "day", "since": "30 days", "step": "1 day"},
    Range.week: {"unit": "week", "since": "84 days", "step": "1 week"},
    Range.month: {"unit": "month", "since": "365 days", "step": "1 month"},
}

CYCLE_HOURS = "extract(epoch FROM completed_at - started_at) / 3600.0"

# `range` is used as a query-param name on the endpoints, which shadows the
# builtin inside those functions; capture it here for internal use.
_irange = range


def _now() -> datetime:
    return datetime.now(UTC)


def _ref(anchor: date | None) -> datetime:
    """Reference 'now' for a request: the anchor date (midnight UTC) if given,
    else the real current time. Lets the UI scrub to any past day/week/month."""
    if anchor is None:
        return _now()
    return datetime(anchor.year, anchor.month, anchor.day, tzinfo=UTC)


def _period_bounds(rng: Range, now: datetime) -> tuple[datetime, datetime, datetime, datetime]:
    """(cur_start, cur_end, prev_start, prev_end) for the given range."""
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if rng is Range.day:
        cur_start = midnight
        cur_end = cur_start + timedelta(days=1)
        prev_start = cur_start - timedelta(days=1)
    elif rng is Range.week:
        cur_start = midnight - timedelta(days=midnight.weekday())  # Monday
        cur_end = cur_start + timedelta(weeks=1)
        prev_start = cur_start - timedelta(weeks=1)
    else:  # month
        cur_start = midnight.replace(day=1)
        cur_end = cur_start + relativedelta(months=1)
        prev_start = cur_start - relativedelta(months=1)
    return cur_start, cur_end, prev_start, cur_start


def _delta_pct(cur: float | None, prev: float | None) -> float | None:
    if cur is None or prev is None or prev == 0:
        return None
    return round((cur - prev) / prev * 100, 1)


def _metric(cur: float | None, prev: float | None) -> Metric:
    cur_r = round(cur, 2) if cur is not None else None
    prev_r = round(prev, 2) if prev is not None else None
    return Metric(current=cur_r, previous=prev_r, delta_pct=_delta_pct(cur, prev))


@router.get("/overview", response_model=OverviewResponse)
async def overview(
    range: Range = Query(default=Range.week),
    anchor: date | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> OverviewResponse:
    cs, ce, ps, pe = _period_bounds(range, _ref(anchor))
    params = {"cs": cs, "ce": ce, "ps": ps, "pe": pe}

    issues_row = (
        await session.execute(
            text(
                f"""
                SELECT
                  count(*) FILTER
                    (WHERE completed_at >= :cs AND completed_at < :ce)::int AS thr_cur,
                  count(*) FILTER
                    (WHERE completed_at >= :ps AND completed_at < :pe)::int AS thr_prev,
                  avg({CYCLE_HOURS}) FILTER (
                    WHERE completed_at >= :cs AND completed_at < :ce AND started_at IS NOT NULL
                  ) AS cyc_cur,
                  avg({CYCLE_HOURS}) FILTER (
                    WHERE completed_at >= :ps AND completed_at < :pe AND started_at IS NOT NULL
                  ) AS cyc_prev,
                  -- WIP as-of the end of the selected period (works for past days too)
                  count(*) FILTER (
                    WHERE started_at < :ce
                      AND (completed_at IS NULL OR completed_at >= :ce)
                      AND (canceled_at IS NULL OR canceled_at >= :ce)
                  )::int AS wip,
                  count(*) FILTER (
                    WHERE state_type IS NOT NULL AND state_type NOT IN ('completed', 'canceled')
                  )::int AS open_issues
                FROM issues
                """
            ),
            params,
        )
    ).mappings().one()

    comments_row = (
        await session.execute(
            text(
                """
                SELECT
                  count(*) FILTER (WHERE created_at >= :cs AND created_at < :ce)::int AS c_cur,
                  count(*) FILTER (WHERE created_at >= :ps AND created_at < :pe)::int AS c_prev
                FROM comments
                """
            ),
            params,
        )
    ).mappings().one()

    return OverviewResponse(
        range=range,
        period_start=cs,
        period_end=ce,
        throughput=_metric(issues_row["thr_cur"], issues_row["thr_prev"]),
        avg_cycle_hours=_metric(issues_row["cyc_cur"], issues_row["cyc_prev"]),
        comments=_metric(comments_row["c_cur"], comments_row["c_prev"]),
        wip=issues_row["wip"],
        open_issues=issues_row["open_issues"],
    )


@router.get("/throughput", response_model=ThroughputResponse)
async def throughput(
    range: Range = Query(default=Range.week),
    anchor: date | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> ThroughputResponse:
    cfg = TREND[range]
    rows = (
        await session.execute(
            text(
                f"""
                WITH spine AS (
                  SELECT gs::date AS period
                  FROM generate_series(
                    date_trunc('{cfg["unit"]}', CAST(:anchor AS timestamptz))
                      - interval '{cfg["since"]}',
                    date_trunc('{cfg["unit"]}', CAST(:anchor AS timestamptz)),
                    interval '{cfg["step"]}'
                  ) gs
                )
                SELECT
                  s.period,
                  COALESCE(c.value, 0)::int AS completed,
                  COALESCE(cr.value, 0)::int AS created
                FROM spine s
                LEFT JOIN (
                  SELECT date_trunc('{cfg["unit"]}', completed_at)::date AS period,
                         count(*) AS value
                  FROM issues WHERE completed_at IS NOT NULL GROUP BY 1
                ) c ON c.period = s.period
                LEFT JOIN (
                  SELECT date_trunc('{cfg["unit"]}', created_at)::date AS period,
                         count(*) AS value
                  FROM issues WHERE created_at IS NOT NULL GROUP BY 1
                ) cr ON cr.period = s.period
                ORDER BY s.period
                """
            ),
            {"anchor": _ref(anchor).date()},
        )
    ).mappings().all()
    return ThroughputResponse(
        range=range,
        unit=cfg["unit"],
        series=[
            DualPoint(period=r["period"], completed=r["completed"], created=r["created"])
            for r in rows
        ],
    )


@router.get("/throughput-by-actor", response_model=ThroughputByActorResponse)
async def throughput_by_actor(
    range: Range = Query(default=Range.week),
    anchor: date | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> ThroughputByActorResponse:
    """Per-person time-series of issues completed and created."""
    cfg = TREND[range]
    ref = _ref(anchor)
    cs, ce, _, _ = _period_bounds(range, ref)

    # Fetch all actors who had any activity (completed or created) in the window.
    actor_rows = (
        await session.execute(
            text(
                """
                SELECT DISTINCT a.id AS actor_id, a.name, a.email
                FROM actors a
                WHERE
                  EXISTS (
                    SELECT 1 FROM issues i
                    WHERE i.assignee_id = a.id
                      AND i.completed_at >= :cs AND i.completed_at < :ce
                  )
                  OR EXISTS (
                    SELECT 1 FROM issues i
                    WHERE i.creator_id = a.id
                      AND i.created_at >= :cs AND i.created_at < :ce
                  )
                ORDER BY a.name
                """
            ),
            {"cs": cs, "ce": ce},
        )
    ).mappings().all()

    if not actor_rows:
        return ThroughputByActorResponse(range=range, unit=cfg["unit"], actors=[])

    actor_ids = [r["actor_id"] for r in actor_rows]

    # Per-actor completed per period.
    comp_rows = (
        await session.execute(
            text(
                f"""
                WITH spine AS (
                  SELECT gs::date AS period
                  FROM generate_series(
                    date_trunc('{cfg["unit"]}', CAST(:anchor AS timestamptz))
                      - interval '{cfg["since"]}',
                    date_trunc('{cfg["unit"]}', CAST(:anchor AS timestamptz)),
                    interval '{cfg["step"]}'
                  ) gs
                )
                SELECT
                  a_id,
                  s.period,
                  COALESCE(count(i.id), 0)::int AS completed
                FROM spine s
                CROSS JOIN unnest(CAST(:actor_ids AS bigint[])) AS t(a_id)
                LEFT JOIN issues i
                  ON i.assignee_id = t.a_id
                  AND date_trunc('{cfg["unit"]}', i.completed_at)::date = s.period
                  AND i.completed_at IS NOT NULL
                GROUP BY a_id, s.period
                ORDER BY a_id, s.period
                """
            ),
            {"anchor": ref.date(), "actor_ids": actor_ids},
        )
    ).mappings().all()

    # Per-actor created per period.
    crea_rows = (
        await session.execute(
            text(
                f"""
                WITH spine AS (
                  SELECT gs::date AS period
                  FROM generate_series(
                    date_trunc('{cfg["unit"]}', CAST(:anchor AS timestamptz))
                      - interval '{cfg["since"]}',
                    date_trunc('{cfg["unit"]}', CAST(:anchor AS timestamptz)),
                    interval '{cfg["step"]}'
                  ) gs
                )
                SELECT
                  a_id,
                  s.period,
                  COALESCE(count(i.id), 0)::int AS created
                FROM spine s
                CROSS JOIN unnest(CAST(:actor_ids AS bigint[])) AS t(a_id)
                LEFT JOIN issues i
                  ON i.creator_id = t.a_id
                  AND date_trunc('{cfg["unit"]}', i.created_at)::date = s.period
                  AND i.created_at IS NOT NULL
                GROUP BY a_id, s.period
                ORDER BY a_id, s.period
                """
            ),
            {"anchor": ref.date(), "actor_ids": actor_ids},
        )
    ).mappings().all()

    # Merge completed + created per (actor, period).
    from collections import defaultdict

    merged: dict[int, dict[date, dict]] = defaultdict(dict)
    for r in comp_rows:
        merged[r["a_id"]].setdefault(r["period"], {"completed": 0, "created": 0})
        merged[r["a_id"]][r["period"]]["completed"] = r["completed"]
    for r in crea_rows:
        merged[r["a_id"]].setdefault(r["period"], {"completed": 0, "created": 0})
        merged[r["a_id"]][r["period"]]["created"] = r["created"]

    actors_out = []
    for ar in actor_rows:
        aid = ar["actor_id"]
        periods = sorted(merged.get(aid, {}).keys())
        series = [
            ActorThroughputPoint(
                period=p,
                completed=merged[aid][p]["completed"],
                created=merged[aid][p]["created"],
            )
            for p in periods
        ]
        actors_out.append(
            ActorThroughputStat(
                actor_id=aid,
                name=ar["name"],
                email=ar["email"],
                series=series,
            )
        )

    return ThroughputByActorResponse(range=range, unit=cfg["unit"], actors=actors_out)


@router.get("/cycle-time", response_model=CycleTimeResponse)
async def cycle_time(
    range: Range = Query(default=Range.week),
    anchor: date | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> CycleTimeResponse:
    cfg = TREND[range]
    rows = (
        await session.execute(
            text(
                f"""
                WITH spine AS (
                  SELECT gs::date AS period
                  FROM generate_series(
                    date_trunc('{cfg["unit"]}', CAST(:anchor AS timestamptz))
                      - interval '{cfg["since"]}',
                    date_trunc('{cfg["unit"]}', CAST(:anchor AS timestamptz)),
                    interval '{cfg["step"]}'
                  ) gs
                )
                SELECT s.period, c.avg_hours, c.median_hours
                FROM spine s
                LEFT JOIN (
                  SELECT date_trunc('{cfg["unit"]}', completed_at)::date AS period,
                         avg({CYCLE_HOURS}) AS avg_hours,
                         percentile_cont(0.5) WITHIN GROUP (ORDER BY {CYCLE_HOURS}) AS median_hours
                  FROM issues
                  WHERE completed_at IS NOT NULL AND started_at IS NOT NULL
                  GROUP BY 1
                ) c ON c.period = s.period
                ORDER BY s.period
                """
            ),
            {"anchor": _ref(anchor).date()},
        )
    ).mappings().all()
    return CycleTimeResponse(
        range=range,
        unit=cfg["unit"],
        series=[
            CycleTimePoint(
                period=r["period"],
                avg_hours=round(r["avg_hours"], 2) if r["avg_hours"] is not None else None,
                median_hours=round(r["median_hours"], 2) if r["median_hours"] is not None else None,
            )
            for r in rows
        ],
    )


@router.get("/wip", response_model=WipResponse)
async def wip(
    range: Range = Query(default=Range.week),
    anchor: date | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> WipResponse:
    cfg = TREND[range]
    ref = _ref(anchor)
    # WIP as-of the end of the selected period (the day after the anchor day, etc.).
    _, ce, _, _ = _period_bounds(range, ref)
    current = (
        await session.execute(
            text(
                """
                SELECT count(*)::int FROM issues
                WHERE started_at < :ce
                  AND (completed_at IS NULL OR completed_at >= :ce)
                  AND (canceled_at IS NULL OR canceled_at >= :ce)
                """
            ),
            {"ce": ce},
        )
    ).scalar_one()
    rows = (
        await session.execute(
            text(
                f"""
                WITH spine AS (
                  SELECT gs AS period_start, gs + interval '{cfg["step"]}' AS period_end
                  FROM generate_series(
                    date_trunc('{cfg["unit"]}', CAST(:anchor AS timestamptz))
                      - interval '{cfg["since"]}',
                    date_trunc('{cfg["unit"]}', CAST(:anchor AS timestamptz)),
                    interval '{cfg["step"]}'
                  ) gs
                )
                SELECT s.period_start::date AS period,
                  (SELECT count(*) FROM issues i
                     WHERE i.started_at IS NOT NULL
                       AND i.started_at < s.period_end
                       AND (i.completed_at IS NULL OR i.completed_at >= s.period_start)
                       AND (i.canceled_at IS NULL OR i.canceled_at >= s.period_start)
                  )::int AS value
                FROM spine s ORDER BY s.period_start
                """
            ),
            {"anchor": ref.date()},
        )
    ).mappings().all()
    return WipResponse(
        range=range,
        unit=cfg["unit"],
        current=current,
        series=[TimeseriesPoint(period=r["period"], value=r["value"]) for r in rows],
    )


@router.get("/by-actor", response_model=ByActorResponse)
async def by_actor(
    range: Range = Query(default=Range.week),
    anchor: date | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> ByActorResponse:
    ref = _ref(anchor)
    cs, ce, _, _ = _period_bounds(range, ref)
    rows = (
        await session.execute(
            text(
                """
                SELECT a.id AS actor_id, a.name, a.email, a.avatar_url,
                  COALESCE(sum(d.throughput), 0)::int AS throughput,
                  CASE WHEN COALESCE(sum(d.throughput), 0) > 0
                       THEN sum(d.avg_cycle_hours * d.throughput) / NULLIF(sum(d.throughput), 0)
                  END AS avg_cycle_hours,
                  COALESCE(sum(d.comments), 0)::int AS comments
                FROM actors a
                LEFT JOIN daily_actor_rollup d
                  ON d.actor_id = a.id AND d.day >= :cs_date AND d.day < :ce_date
                GROUP BY a.id, a.name, a.email, a.avatar_url
                HAVING COALESCE(sum(d.throughput), 0) > 0 OR COALESCE(sum(d.comments), 0) > 0
                  -- also include actors who only created issues (creator_id) in the window
                  OR a.id IN (
                    SELECT DISTINCT creator_id FROM issues
                    WHERE creator_id IS NOT NULL
                      AND created_at >= :cs AND created_at < :ce
                  )
                ORDER BY throughput DESC, comments DESC
                """
            ),
            {"cs_date": cs.date(), "ce_date": ce.date(), "cs": cs, "ce": ce},
        )
    ).mappings().all()

    # Sparkline: daily throughput for the 14 days ending at the anchor, per actor.
    spark_end = ref.date()
    spark_start = spark_end - timedelta(days=13)
    spark_rows = (
        await session.execute(
            text(
                "SELECT actor_id, day, throughput FROM daily_actor_rollup "
                "WHERE day >= :start AND day <= :end"
            ),
            {"start": spark_start, "end": spark_end},
        )
    ).mappings().all()
    spark: dict[int, dict[date, int]] = {}
    for r in spark_rows:
        spark.setdefault(r["actor_id"], {})[r["day"]] = r["throughput"]
    days = [spark_start + timedelta(days=i) for i in _irange(14)]

    actors = [
        ActorStat(
            actor_id=r["actor_id"],
            name=r["name"],
            email=r["email"],
            avatar_url=r["avatar_url"],
            throughput=r["throughput"],
            avg_cycle_hours=round(r["avg_cycle_hours"], 2)
            if r["avg_cycle_hours"] is not None
            else None,
            comments=r["comments"],
            sparkline=[spark.get(r["actor_id"], {}).get(d, 0) for d in days],
        )
        for r in rows
    ]
    return ByActorResponse(range=range, period_start=cs, period_end=ce, actors=actors)


@router.get("/by-team", response_model=ByTeamResponse)
async def by_team(
    range: Range = Query(default=Range.week),
    anchor: date | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> ByTeamResponse:
    ref = _ref(anchor)
    if range is Range.month:
        view, col = "monthly_team_rollup", "month_start"
        period_start = ref.date().replace(day=1)
    else:
        view, col = "weekly_team_rollup", "week_start"
        period_start = ref.date() - timedelta(days=ref.weekday())

    rows = (
        await session.execute(
            text(
                f"""
                SELECT t.id AS team_id, t.name, t.key,
                  COALESCE(r.throughput, 0)::int AS throughput,
                  r.avg_cycle_hours, r.median_cycle_hours,
                  COALESCE(r.wip, 0)::int AS wip,
                  COALESCE(r.comments, 0)::int AS comments,
                  COALESCE(r.scope_added, 0)::int AS scope_added
                FROM teams t
                LEFT JOIN {view} r ON r.team_id = t.id AND r.{col} = :period_start
                ORDER BY throughput DESC, t.name
                """
            ),
            {"period_start": period_start},
        )
    ).mappings().all()

    teams = [
        TeamStat(
            team_id=r["team_id"],
            name=r["name"],
            key=r["key"],
            throughput=r["throughput"],
            avg_cycle_hours=round(r["avg_cycle_hours"], 2)
            if r["avg_cycle_hours"] is not None
            else None,
            median_cycle_hours=round(r["median_cycle_hours"], 2)
            if r["median_cycle_hours"] is not None
            else None,
            wip=r["wip"],
            comments=r["comments"],
            scope_added=r["scope_added"],
        )
        for r in rows
    ]
    return ByTeamResponse(range=range, period_start=period_start, teams=teams)
