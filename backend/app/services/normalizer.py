"""Normalize Linear DTOs into the typed tables.

Each entity is first landed append-only in ``raw_events`` (payload = the original
GraphQL node), then upserted (ON CONFLICT DO UPDATE keyed on linear_id). Issue
state transitions are derived by comparing the incoming state against what is
already stored — so the pipeline is fully idempotent and overlap-safe (re-syncing
the same record produces no duplicate transition because, post-upsert, the stored
state already equals the incoming one).

Surrogate FK ids are resolved from linear_id via lookup maps read from the DB,
so references resolve even when the referenced row was ingested on a prior run.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import func, select, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db_partitions import ensure_month_partition
from app.linear.client import (
    LinearComment,
    LinearCycle,
    LinearIssue,
    LinearLabel,
    LinearTeam,
    LinearUser,
)
from app.models import (
    Actor,
    Comment,
    Cycle,
    Issue,
    IssueHistory,
    IssueTag,
    IssueTagHistory,
    RawEvent,
    Tag,
    Team,
)

logger = logging.getLogger("app.normalizer")


async def _land_raw(session: AsyncSession, event_type: str, dtos: Iterable) -> None:
    rows = [{"event_type": event_type, "action": "sync", "payload": d.raw} for d in dtos]
    if rows:
        await session.execute(pg_insert(RawEvent), rows)


async def _id_map(session: AsyncSession, model) -> dict[str, int]:
    res = await session.execute(select(model.linear_id, model.id))
    return {linear_id: surrogate for linear_id, surrogate in res.all()}


async def upsert_teams(session: AsyncSession, teams: list[LinearTeam]) -> int:
    if not teams:
        return 0
    await _land_raw(session, "Team", teams)
    rows = [
        {"linear_id": t.id, "key": t.key, "name": t.name, "archived_at": t.archived_at}
        for t in teams
    ]
    stmt = pg_insert(Team).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Team.linear_id],
        set_={
            "key": stmt.excluded.key,
            "name": stmt.excluded.name,
            "archived_at": stmt.excluded.archived_at,
            "row_updated_at": func.now(),
        },
    )
    await session.execute(stmt)
    return len(rows)


async def upsert_actors(session: AsyncSession, users: list[LinearUser]) -> int:
    if not users:
        return 0
    await _land_raw(session, "User", users)
    rows = [
        {
            "linear_id": u.id,
            "name": u.name,
            "email": u.email,
            "avatar_url": u.avatar_url,
            "active": u.active,
        }
        for u in users
    ]
    stmt = pg_insert(Actor).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Actor.linear_id],
        set_={
            "name": stmt.excluded.name,
            "email": stmt.excluded.email,
            "avatar_url": stmt.excluded.avatar_url,
            "active": stmt.excluded.active,
            "row_updated_at": func.now(),
        },
    )
    await session.execute(stmt)
    return len(rows)


async def upsert_cycles(session: AsyncSession, cycles: list[LinearCycle]) -> int:
    if not cycles:
        return 0
    await _land_raw(session, "Cycle", cycles)
    team_map = await _id_map(session, Team)
    rows = [
        {
            "linear_id": c.id,
            "team_id": team_map.get(c.team_id),
            "number": c.number,
            "name": c.name,
            "starts_at": c.starts_at,
            "ends_at": c.ends_at,
            "completed_at": c.completed_at,
        }
        for c in cycles
    ]
    stmt = pg_insert(Cycle).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Cycle.linear_id],
        set_={
            "team_id": stmt.excluded.team_id,
            "number": stmt.excluded.number,
            "name": stmt.excluded.name,
            "starts_at": stmt.excluded.starts_at,
            "ends_at": stmt.excluded.ends_at,
            "completed_at": stmt.excluded.completed_at,
            "row_updated_at": func.now(),
        },
    )
    await session.execute(stmt)
    return len(rows)


async def upsert_issues(session: AsyncSession, issues: list[LinearIssue]) -> tuple[int, int]:
    """Upsert issues and record state transitions. Returns (upserted, transitions)."""
    if not issues:
        return 0, 0
    await _land_raw(session, "Issue", issues)

    team_map = await _id_map(session, Team)
    actor_map = await _id_map(session, Actor)
    cycle_map = await _id_map(session, Cycle)

    # Snapshot stored state BEFORE upserting so we can diff transitions.
    res = await session.execute(
        select(Issue.linear_id, Issue.state, Issue.state_type)
    )
    stored = {lid: (st, stt) for lid, st, stt in res.all()}

    transitions: list[dict] = []
    for it in issues:
        prev = stored.get(it.id)
        changed_at = it.updated_at or it.created_at or datetime.now(UTC)
        if prev is None:
            # New issue: record an initial (null -> current) baseline transition.
            transitions.append(
                {
                    "issue_linear_id": it.id,
                    "changed_at": changed_at,
                    "from_state": None,
                    "from_state_type": None,
                    "to_state": it.state,
                    "to_state_type": it.state_type,
                }
            )
        elif prev[0] != it.state or prev[1] != it.state_type:
            transitions.append(
                {
                    "issue_linear_id": it.id,
                    "changed_at": changed_at,
                    "from_state": prev[0],
                    "from_state_type": prev[1],
                    "to_state": it.state,
                    "to_state_type": it.state_type,
                }
            )

    rows = [
        {
            "linear_id": it.id,
            "identifier": it.identifier,
            "title": it.title,
            "team_id": team_map.get(it.team_id),
            "assignee_id": actor_map.get(it.assignee_id),
            "creator_id": actor_map.get(it.creator_id),
            "cycle_id": cycle_map.get(it.cycle_id),
            "state": it.state,
            "state_type": it.state_type,
            "priority": it.priority,
            "estimate": it.estimate,
            "project_id": it.project_id,
            "created_at": it.created_at,
            "started_at": it.started_at,
            "completed_at": it.completed_at,
            "canceled_at": it.canceled_at,
            "updated_at": it.updated_at,
        }
        for it in issues
    ]
    stmt = pg_insert(Issue).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Issue.linear_id],
        set_={
            c: getattr(stmt.excluded, c)
            for c in (
                "identifier", "title", "team_id", "assignee_id", "creator_id",
                "cycle_id", "state", "state_type", "priority", "estimate",
                "project_id", "created_at", "started_at", "completed_at",
                "canceled_at", "updated_at",
            )
        }
        | {"row_updated_at": func.now()},
    )
    await session.execute(stmt)

    n_transitions = await _write_transitions(session, transitions, actor_map=actor_map)
    return len(rows), n_transitions


async def _write_transitions(
    session: AsyncSession, transitions: list[dict], *, actor_map: dict[str, int]
) -> int:
    if not transitions:
        return 0
    # Resolve issue surrogate ids now that all issues are upserted.
    issue_map = await _id_map(session, Issue)

    # Ensure a monthly partition exists for every changed_at month before inserting.
    conn = await session.connection()
    months = {(t["changed_at"].year, t["changed_at"].month) for t in transitions}
    for year, month in sorted(months):
        await ensure_month_partition(conn, "issue_history", datetime(year, month, 1, tzinfo=UTC))

    rows = []
    for t in transitions:
        issue_id = issue_map.get(t["issue_linear_id"])
        if issue_id is None:
            continue
        rows.append(
            {
                "issue_id": issue_id,
                "changed_at": t["changed_at"],
                "linear_id": None,  # compare-based; no Linear history node id
                "actor_id": None,   # actor unknown without history API
                "from_state": t["from_state"],
                "from_state_type": t["from_state_type"],
                "to_state": t["to_state"],
                "to_state_type": t["to_state_type"],
            }
        )
    if rows:
        await session.execute(pg_insert(IssueHistory), rows)
    return len(rows)


async def upsert_comments(session: AsyncSession, comments: list[LinearComment]) -> int:
    if not comments:
        return 0
    await _land_raw(session, "Comment", comments)
    issue_map = await _id_map(session, Issue)
    actor_map = await _id_map(session, Actor)

    rows = []
    skipped = 0
    for c in comments:
        issue_id = issue_map.get(c.issue_id)
        if issue_id is None:
            skipped += 1  # comment on an issue we have not ingested; skip (issue_id is NOT NULL)
            continue
        rows.append(
            {
                "linear_id": c.id,
                "issue_id": issue_id,
                "actor_id": actor_map.get(c.user_id),
                "body": c.body,
                "created_at": c.created_at,
            }
        )
    if skipped:
        logger.warning("Skipped %d comments referencing unknown issues", skipped)
    if not rows:
        return 0
    stmt = pg_insert(Comment).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Comment.linear_id],
        set_={
            "issue_id": stmt.excluded.issue_id,
            "actor_id": stmt.excluded.actor_id,
            "body": stmt.excluded.body,
            "created_at": stmt.excluded.created_at,
            "row_updated_at": func.now(),
        },
    )
    await session.execute(stmt)
    return len(rows)


async def upsert_labels(session: AsyncSession, labels: list[LinearLabel]) -> int:
    """Upsert the label dictionary into `tags` — the dimension the
    Engineering Points system (app/jobs/score_points.py) reads."""
    if not labels:
        return 0
    await _land_raw(session, "IssueLabel", labels)
    team_map = await _id_map(session, Team)
    actor_map = await _id_map(session, Actor)
    rows = [
        {
            "linear_id": lbl.id,
            "team_id": team_map.get(lbl.team_id),
            "name": lbl.name,
            "color_code": lbl.color,
            "created_by_id": actor_map.get(lbl.creator_id),
        }
        for lbl in labels
    ]
    stmt = pg_insert(Tag).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Tag.linear_id],
        set_={
            "team_id": stmt.excluded.team_id,
            "name": stmt.excluded.name,
            "color_code": stmt.excluded.color_code,
            "created_by_id": stmt.excluded.created_by_id,
            "row_updated_at": func.now(),
        },
    )
    await session.execute(stmt)
    return len(rows)


async def upsert_issue_tags(session: AsyncSession, issues: list[LinearIssue]) -> tuple[int, int]:
    """Diff each issue's incoming label set against `issue_tags`, upsert the
    current-state table, and append add/remove rows to `issue_tag_history`.

    Same snapshot-before-overwrite-then-diff idiom `upsert_issues` already
    uses for (state, state_type), applied to label SETS instead — the one
    genuinely new piece this port adds. `changed_at` is this poll's
    timestamp, not the label's true edit instant (Linear has no bulk
    label-history API), same limitation issue_history already accepts for
    state transitions. Returns (issue_tags rows touched, history rows written).
    """
    if not issues:
        return 0, 0
    issue_map = await _id_map(session, Issue)
    tag_map = await _id_map(session, Tag)

    incoming: dict[int, set[int]] = {}
    for it in issues:
        issue_id = issue_map.get(it.id)
        if issue_id is None:
            continue
        incoming[issue_id] = {tag_map[lid] for lid in it.label_ids if lid in tag_map}

    if not incoming:
        return 0, 0

    res = await session.execute(
        select(IssueTag.issue_id, IssueTag.tag_id).where(
            IssueTag.issue_id.in_(incoming.keys()), IssueTag.removed_at.is_(None)
        )
    )
    current: dict[int, set[int]] = {}
    for issue_id, tag_id in res.all():
        current.setdefault(issue_id, set()).add(tag_id)

    now = datetime.now(UTC)
    added_pairs: list[tuple[int, int]] = []
    removed_pairs: list[tuple[int, int]] = []
    for issue_id, want in incoming.items():
        have = current.get(issue_id, set())
        added_pairs.extend((issue_id, tag_id) for tag_id in want - have)
        removed_pairs.extend((issue_id, tag_id) for tag_id in have - want)

    if added_pairs:
        stmt = pg_insert(IssueTag).values(
            [
                {"issue_id": i, "tag_id": t, "added_at": now, "removed_at": None}
                for i, t in added_pairs
            ]
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[IssueTag.issue_id, IssueTag.tag_id],
            set_={"added_at": now, "removed_at": None},
        )
        await session.execute(stmt)

    if removed_pairs:
        await session.execute(
            IssueTag.__table__.update()
            .where(tuple_(IssueTag.issue_id, IssueTag.tag_id).in_(removed_pairs))
            .values(removed_at=now)
        )

    history_rows = [
        {"issue_id": i, "tag_id": t, "action": "added", "changed_at": now}
        for i, t in added_pairs
    ] + [
        {"issue_id": i, "tag_id": t, "action": "removed", "changed_at": now}
        for i, t in removed_pairs
    ]
    if history_rows:
        conn = await session.connection()
        await ensure_month_partition(conn, "issue_tag_history", now)
        await session.execute(pg_insert(IssueTagHistory), history_rows)

    return len(added_pairs) + len(removed_pairs), len(history_rows)
