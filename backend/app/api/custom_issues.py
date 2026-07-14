"""Custom issues API — track non-Linear work items (e.g. "set up AWS") that
still need to count toward throughput, WIP, and per-person/team tallies.

Custom issues are stored as ordinary rows in the `issues` table with
`source = 'custom'`, so every existing insights query (overview, throughput,
by-actor, by-team) picks them up automatically alongside synced Linear
issues — no separate aggregation path.

Endpoints:
  GET    /api/custom-issues/actors          — all known actors (for the dropdown)
  GET    /api/custom-issues/list            — list custom issues
  POST   /api/custom-issues/create          — create a custom issue
  PATCH  /api/custom-issues/{issue_id}      — update title / assignee / status
  DELETE /api/custom-issues/{issue_id}      — delete a custom issue
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_token
from app.db import get_session
from app.schemas.custom_issues import (
    ActorOut,
    CustomIssueCreate,
    CustomIssueListResp,
    CustomIssueOut,
    CustomIssueStatus,
    CustomIssueUpdate,
)

router = APIRouter(
    prefix="/api/custom-issues",
    tags=["custom-issues"],
    dependencies=[Depends(require_token)],
)

IDENTIFIER_PREFIX = "INT"  # "internal" — distinguishes custom issues from Linear's TEAM-123 style


def _now() -> datetime:
    return datetime.now(UTC)


def _status_timestamps(status_: CustomIssueStatus, now: datetime) -> dict:
    """started_at/completed_at/canceled_at implied by a status value."""
    return {
        "started_at": now if status_ in (CustomIssueStatus.started, CustomIssueStatus.completed) else None,
        "completed_at": now if status_ is CustomIssueStatus.completed else None,
        "canceled_at": now if status_ is CustomIssueStatus.canceled else None,
    }


def _row_out(row: dict) -> CustomIssueOut:
    return CustomIssueOut(
        id=row["id"],
        identifier=row["identifier"],
        title=row["title"],
        assignee_id=row["assignee_id"],
        assignee_name=row.get("assignee_name"),
        assignee_email=row.get("assignee_email"),
        status=row["state_type"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        canceled_at=row["canceled_at"],
    )


# ---------------------------------------------------------------------------
# GET /actors — assignee picker dropdown
# ---------------------------------------------------------------------------
@router.get("/actors", response_model=list[ActorOut])
async def list_actors(session: AsyncSession = Depends(get_session)) -> list[ActorOut]:
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
# GET / — list custom issues
# ---------------------------------------------------------------------------
@router.get("/list", response_model=CustomIssueListResp)
async def list_custom_issues(
    status_: CustomIssueStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> CustomIssueListResp:
    status_filter = "AND i.state_type = :status" if status_ is not None else ""
    params = {"lim": limit, "off": offset}
    if status_ is not None:
        params["status"] = status_.value

    rows = (
        await session.execute(
            text(
                f"""
                SELECT i.id, i.identifier, i.title, i.assignee_id, i.state_type,
                       i.created_at, i.started_at, i.completed_at, i.canceled_at,
                       a.name AS assignee_name, a.email AS assignee_email
                FROM issues i
                LEFT JOIN actors a ON a.id = i.assignee_id
                WHERE i.source = 'custom'
                {status_filter}
                ORDER BY i.created_at DESC
                LIMIT :lim OFFSET :off
                """
            ),
            params,
        )
    ).mappings().all()

    total_row = (
        await session.execute(
            text(f"SELECT count(*)::int AS n FROM issues i WHERE i.source = 'custom' {status_filter}"),
            {k: v for k, v in params.items() if k != "lim" and k != "off"},
        )
    ).mappings().one()

    return CustomIssueListResp(issues=[_row_out(dict(r)) for r in rows], total=total_row["n"])


# ---------------------------------------------------------------------------
# POST / — create a custom issue
# ---------------------------------------------------------------------------
@router.post("/create", response_model=CustomIssueOut, status_code=status.HTTP_201_CREATED)
async def create_custom_issue(
    body: CustomIssueCreate,
    session: AsyncSession = Depends(get_session),
) -> CustomIssueOut:
    now = _now()
    linear_id = f"custom-{uuid.uuid4()}"

    seq = (
        await session.execute(
            text("SELECT count(*)::int + 1 AS n FROM issues WHERE source = 'custom'")
        )
    ).scalar_one()
    identifier = f"{IDENTIFIER_PREFIX}-{seq}"

    ts = _status_timestamps(body.status, now)
    row = (
        await session.execute(
            text(
                """
                INSERT INTO issues (
                    linear_id, identifier, title, assignee_id, creator_id,
                    state, state_type, source, created_at, updated_at,
                    started_at, completed_at, canceled_at
                ) VALUES (
                    :linear_id, :identifier, :title, :assignee_id, :assignee_id,
                    :state, :state, 'custom', :now, :now,
                    :started_at, :completed_at, :canceled_at
                )
                RETURNING id, identifier, title, assignee_id, state_type,
                          created_at, started_at, completed_at, canceled_at
                """
            ),
            {
                "linear_id": linear_id,
                "identifier": identifier,
                "title": body.title,
                "assignee_id": body.assignee_id,
                "state": body.status.value,
                "now": now,
                "started_at": ts["started_at"],
                "completed_at": ts["completed_at"],
                "canceled_at": ts["canceled_at"],
            },
        )
    ).mappings().one()
    await session.commit()

    actor = (
        await session.execute(
            text("SELECT name, email FROM actors WHERE id = :id"),
            {"id": body.assignee_id},
        )
    ).mappings().first() if body.assignee_id is not None else None

    return _row_out(
        {**dict(row), "assignee_name": actor["name"] if actor else None,
         "assignee_email": actor["email"] if actor else None}
    )


# ---------------------------------------------------------------------------
# PATCH /{issue_id} — update title / assignee / status
# ---------------------------------------------------------------------------
@router.patch("/{issue_id}", response_model=CustomIssueOut)
async def update_custom_issue(
    issue_id: int,
    body: CustomIssueUpdate,
    session: AsyncSession = Depends(get_session),
) -> CustomIssueOut:
    existing = (
        await session.execute(
            text("SELECT id FROM issues WHERE id = :id AND source = 'custom'"),
            {"id": issue_id},
        )
    ).mappings().first()
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Custom issue not found.")

    now = _now()
    fields: dict = {}
    if body.title is not None:
        fields["title"] = body.title
    if body.assignee_id is not None:
        fields["assignee_id"] = body.assignee_id
    if body.status is not None:
        fields["state"] = body.status.value
        fields["state_type"] = body.status.value
        ts = _status_timestamps(body.status, now)
        fields.update(ts)
    fields["updated_at"] = now

    if not fields:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update.")

    set_clause = ", ".join(f"{k} = :{k}" for k in fields)
    row = (
        await session.execute(
            text(
                f"""
                UPDATE issues SET {set_clause}
                WHERE id = :id AND source = 'custom'
                RETURNING id, identifier, title, assignee_id, state_type,
                          created_at, started_at, completed_at, canceled_at
                """
            ),
            {**fields, "id": issue_id},
        )
    ).mappings().one()
    await session.commit()

    actor = (
        await session.execute(
            text("SELECT name, email FROM actors WHERE id = :id"),
            {"id": row["assignee_id"]},
        )
    ).mappings().first() if row["assignee_id"] is not None else None

    return _row_out(
        {**dict(row), "assignee_name": actor["name"] if actor else None,
         "assignee_email": actor["email"] if actor else None}
    )


# ---------------------------------------------------------------------------
# DELETE /{issue_id} — delete a custom issue
# ---------------------------------------------------------------------------
@router.delete("/{issue_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_custom_issue(
    issue_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    result = await session.execute(
        text("DELETE FROM issues WHERE id = :id AND source = 'custom'"),
        {"id": issue_id},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Custom issue not found.")
    await session.commit()
