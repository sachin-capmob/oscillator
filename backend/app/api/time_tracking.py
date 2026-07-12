"""Time-tracking API — clock in / clock out for Linear team members.

Endpoints:
  GET  /api/time/actors              — all known actors (for the UI dropdown)
  POST /api/time/start               — start a timer for an actor
  POST /api/time/stop/{entry_id}     — stop a running timer
  GET  /api/time/active              — get the running timer for an actor
  GET  /api/time/entries             — paginated list of completed entries
  GET  /api/time/summary             — total seconds + session count per actor
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_token
from app.db import get_session
from app.schemas.time_tracking import (
    ActiveTimerResp,
    ActorOut,
    TimeEntryOut,
    TimeEntryStart,
    TimeEntryStop,
    TimeLogResp,
    TimeSummaryItem,
    TimeSummaryResp,
)

router = APIRouter(
    prefix="/api/time",
    tags=["time-tracking"],
    dependencies=[Depends(require_token)],
)


def _now() -> datetime:
    return datetime.now(UTC)


def _entry_from_row(row: dict) -> TimeEntryOut:
    """Build a TimeEntryOut from a DB row mapping."""
    started: datetime = row["started_at"]
    stopped: datetime | None = row["stopped_at"]
    duration: int | None = None
    if stopped is not None:
        duration = int((stopped - started).total_seconds())
    return TimeEntryOut(
        id=row["id"],
        actor_id=row["actor_id"],
        actor_name=row.get("actor_name"),
        actor_email=row.get("actor_email"),
        started_at=started,
        stopped_at=stopped,
        duration_secs=duration,
        note=row.get("note"),
    )


# ---------------------------------------------------------------------------
# GET /actors — people picker dropdown
# ---------------------------------------------------------------------------
@router.get("/actors", response_model=list[ActorOut])
async def list_actors(
    session: AsyncSession = Depends(get_session),
) -> list[ActorOut]:
    """Return all known actors sorted by name — used to populate the dropdown."""
    rows = (
        await session.execute(
            text(
                "SELECT id AS actor_id, name, email, avatar_url "
                "FROM actors ORDER BY COALESCE(name, email)"
            )
        )
    ).mappings().all()
    return [ActorOut(**r) for r in rows]


# ---------------------------------------------------------------------------
# POST /start — clock in
# ---------------------------------------------------------------------------
@router.post("/start", response_model=TimeEntryOut, status_code=status.HTTP_201_CREATED)
async def start_timer(
    body: TimeEntryStart,
    session: AsyncSession = Depends(get_session),
) -> TimeEntryOut:
    """Start a new timer for `actor_id`. Returns 409 if one is already running."""
    # Enforce one active timer per actor.
    existing = (
        await session.execute(
            text(
                "SELECT id FROM time_entries "
                "WHERE actor_id = :aid AND stopped_at IS NULL "
                "LIMIT 1"
            ),
            {"aid": body.actor_id},
        )
    ).mappings().first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Actor {body.actor_id} already has a running timer "
                f"(entry id={existing['id']}). Stop it first."
            ),
        )

    now = _now()
    row = (
        await session.execute(
            text(
                """
                INSERT INTO time_entries (actor_id, started_at, note)
                VALUES (:aid, :started, :note)
                RETURNING id, actor_id, started_at, stopped_at, note
                """
            ),
            {"aid": body.actor_id, "started": now, "note": body.note},
        )
    ).mappings().one()
    await session.commit()

    # Fetch actor meta for the response.
    actor = (
        await session.execute(
            text("SELECT name, email FROM actors WHERE id = :id"),
            {"id": body.actor_id},
        )
    ).mappings().first()

    return _entry_from_row(
        {**dict(row), "actor_name": actor["name"] if actor else None,
         "actor_email": actor["email"] if actor else None}
    )


# ---------------------------------------------------------------------------
# POST /stop/{entry_id} — clock out
# ---------------------------------------------------------------------------
@router.post("/stop/{entry_id}", response_model=TimeEntryOut)
async def stop_timer(
    entry_id: int,
    body: TimeEntryStop = TimeEntryStop(),
    session: AsyncSession = Depends(get_session),
) -> TimeEntryOut:
    """Stop a running timer. Returns 404 if not found, 409 if already stopped."""
    existing = (
        await session.execute(
            text(
                """
                SELECT te.id, te.actor_id, te.started_at, te.stopped_at, te.note,
                       a.name AS actor_name, a.email AS actor_email
                FROM time_entries te
                LEFT JOIN actors a ON a.id = te.actor_id
                WHERE te.id = :eid
                """
            ),
            {"eid": entry_id},
        )
    ).mappings().first()

    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Time entry not found.")
    if existing["stopped_at"] is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Timer is already stopped.",
        )

    now = _now()
    note = body.note if body.note is not None else existing["note"]
    updated = (
        await session.execute(
            text(
                """
                UPDATE time_entries
                SET stopped_at = :stopped, note = :note
                WHERE id = :eid
                RETURNING id, actor_id, started_at, stopped_at, note
                """
            ),
            {"stopped": now, "note": note, "eid": entry_id},
        )
    ).mappings().one()
    await session.commit()

    return _entry_from_row(
        {**dict(updated),
         "actor_name": existing["actor_name"],
         "actor_email": existing["actor_email"]}
    )


# ---------------------------------------------------------------------------
# GET /active — currently running timer for an actor
# ---------------------------------------------------------------------------
@router.get("/active", response_model=ActiveTimerResp)
async def active_timer(
    actor_id: int = Query(...),
    session: AsyncSession = Depends(get_session),
) -> ActiveTimerResp:
    """Return the running entry for `actor_id`, or `{entry: null}` if idle."""
    row = (
        await session.execute(
            text(
                """
                SELECT te.id, te.actor_id, te.started_at, te.stopped_at, te.note,
                       a.name AS actor_name, a.email AS actor_email
                FROM time_entries te
                LEFT JOIN actors a ON a.id = te.actor_id
                WHERE te.actor_id = :aid AND te.stopped_at IS NULL
                ORDER BY te.started_at DESC
                LIMIT 1
                """
            ),
            {"aid": actor_id},
        )
    ).mappings().first()

    return ActiveTimerResp(entry=_entry_from_row(dict(row)) if row else None)


# ---------------------------------------------------------------------------
# GET /entries — paginated log of completed sessions
# ---------------------------------------------------------------------------
@router.get("/entries", response_model=TimeLogResp)
async def list_entries(
    actor_id: int | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> TimeLogResp:
    """Paginated list of stopped time entries, most recent first."""
    actor_filter = "AND te.actor_id = :aid" if actor_id is not None else ""

    rows = (
        await session.execute(
            text(
                f"""
                SELECT te.id, te.actor_id, te.started_at, te.stopped_at, te.note,
                       a.name AS actor_name, a.email AS actor_email
                FROM time_entries te
                LEFT JOIN actors a ON a.id = te.actor_id
                WHERE te.stopped_at IS NOT NULL
                {actor_filter}
                ORDER BY te.started_at DESC
                LIMIT :lim OFFSET :off
                """
            ),
            {"aid": actor_id, "lim": limit, "off": offset},
        )
    ).mappings().all()

    total_row = (
        await session.execute(
            text(
                f"""
                SELECT count(*)::int AS n FROM time_entries
                WHERE stopped_at IS NOT NULL {actor_filter}
                """
            ),
            {"aid": actor_id},
        )
    ).mappings().one()

    return TimeLogResp(
        entries=[_entry_from_row(dict(r)) for r in rows],
        total=total_row["n"],
    )


# ---------------------------------------------------------------------------
# GET /summary — aggregated hours per actor
# ---------------------------------------------------------------------------
@router.get("/summary", response_model=TimeSummaryResp)
async def time_summary(
    session: AsyncSession = Depends(get_session),
) -> TimeSummaryResp:
    """Total seconds logged and session count per actor (completed sessions only)."""
    rows = (
        await session.execute(
            text(
                """
                SELECT
                  te.actor_id,
                  a.name  AS actor_name,
                  a.email AS actor_email,
                  COALESCE(sum(
                    extract(epoch FROM te.stopped_at - te.started_at)
                  )::int, 0)           AS total_secs,
                  count(te.id)::int    AS session_count
                FROM time_entries te
                LEFT JOIN actors a ON a.id = te.actor_id
                WHERE te.stopped_at IS NOT NULL
                GROUP BY te.actor_id, a.name, a.email
                ORDER BY total_secs DESC
                """
            )
        )
    ).mappings().all()

    return TimeSummaryResp(
        items=[
            TimeSummaryItem(
                actor_id=r["actor_id"],
                actor_name=r["actor_name"],
                actor_email=r["actor_email"],
                total_secs=r["total_secs"],
                session_count=r["session_count"],
            )
            for r in rows
        ]
    )
