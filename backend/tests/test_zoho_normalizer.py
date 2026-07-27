"""Functional tests for the Zoho Sprints normalizer, especially tag diffing
(upsert_item_tags) — the one genuinely new idiom in this port (everything
else mirrors upsert_issues/_write_transitions exactly).

Requires a real Postgres reachable via DATABASE_URL (skipped otherwise —
these exercise partitioned-table inserts and ON CONFLICT upserts that
sqlite can't emulate). Each phase opens its OWN session/transaction, exactly
like app/jobs/sync.py's run_sync() — reusing one session across sequential
`session.begin()` blocks trips SQLAlchemy's autobegin ("a transaction is
already begun on this Session").
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, text

from app.config import get_settings
from app.db import get_engine, get_sessionmaker
from app.db_partitions import ensure_partitions_around
from app.models import Issue, IssueTag, IssueTagHistory, Tag
from app.services import normalizer
from app.zoho.client import ZohoItem, ZohoProject, ZohoTag, ZohoTeam, ZohoUser

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="requires a live DATABASE_URL"
)


def _item(item_id: str, *, tag_ids: list[str], status_name: str = "Open") -> ZohoItem:
    return ZohoItem.from_node(
        {
            "itemId": item_id,
            "itemName": f"Item {item_id}",
            "projectId": "proj-1",
            "ownerId": "user-1",
            "createdBy": "user-1",
            "statusId": "status-open",
            "statusName": status_name,
            "createdTime": "2026-07-01T00:00:00Z",
            "updatedTime": "2026-07-01T00:00:00Z",
            "tags": [{"tagId": t} for t in tag_ids],
        },
        project_id="proj-1",
    )


@pytest.mark.asyncio
async def test_tag_diffing_add_remove_idempotent():
    get_settings.cache_clear()
    engine = get_engine()
    Session = get_sessionmaker()

    async with engine.begin() as conn:
        await ensure_partitions_around(conn, datetime.now(UTC))

    async with Session() as session:
        async with session.begin():
            for table in (
                "issue_tag_history", "issue_tags", "issues", "tags", "projects", "actors", "teams",
            ):
                await session.execute(text(f"DELETE FROM {table}"))

    # --- seed team / project / actor / two tags (one phase per commit) ---
    async with Session() as session:
        async with session.begin():
            await normalizer.upsert_zoho_teams(
                session, [ZohoTeam.from_node({"teamId": "team-1", "teamName": "Core"})]
            )
    async with Session() as session:
        async with session.begin():
            await normalizer.upsert_projects(
                session,
                [ZohoProject.from_node({"projectId": "proj-1", "projectName": "P1"}, team_id="team-1")],
            )
    async with Session() as session:
        async with session.begin():
            await normalizer.upsert_zoho_actors(
                session, [ZohoUser.from_node({"zuid": "user-1", "name": "Ada"})]
            )
    async with Session() as session:
        async with session.begin():
            await normalizer.upsert_tags(
                session,
                [
                    ZohoTag.from_node({"tagId": "tag-triaged", "tagName": "triaged"}, team_id="team-1"),
                    ZohoTag.from_node({"tagId": "tag-reverted", "tagName": "reverted"}, team_id="team-1"),
                ],
            )

    # --- sync run 1: item carries only "triaged" ---
    items = [_item("item-1", tag_ids=["tag-triaged"])]
    async with Session() as session:
        async with session.begin():
            await normalizer.upsert_items(session, items)
    async with Session() as session:
        async with session.begin():
            n_touched, n_hist = await normalizer.upsert_item_tags(session, items)
        assert n_touched == 1
        assert n_hist == 1

        issue_id = (
            await session.execute(select(Issue.id).where(Issue.zoho_id == "item-1"))
        ).scalar_one()
        tag_id = (
            await session.execute(select(Tag.id).where(Tag.zoho_id == "tag-triaged"))
        ).scalar_one()

        current = (
            await session.execute(
                select(IssueTag.tag_id).where(
                    IssueTag.issue_id == issue_id, IssueTag.removed_at.is_(None)
                )
            )
        ).scalars().all()
        assert current == [tag_id]

        history_actions = (
            await session.execute(
                select(IssueTagHistory.action).where(IssueTagHistory.issue_id == issue_id)
            )
        ).scalars().all()
        assert history_actions == ["added"]

    # --- sync run 2: SAME tag state — must be a no-op (idempotent) ---
    async with Session() as session:
        async with session.begin():
            n_touched, n_hist = await normalizer.upsert_item_tags(session, items)
        assert (n_touched, n_hist) == (0, 0)

        history_count = (
            await session.execute(
                select(func.count()).select_from(IssueTagHistory).where(
                    IssueTagHistory.issue_id == issue_id
                )
            )
        ).scalar_one()
        assert history_count == 1  # unchanged from run 1

    # --- sync run 3: "triaged" removed, "reverted" added ---
    items_v2 = [_item("item-1", tag_ids=["tag-reverted"])]
    async with Session() as session:
        async with session.begin():
            n_touched, n_hist = await normalizer.upsert_item_tags(session, items_v2)
        assert n_touched == 2  # one add, one remove
        assert n_hist == 2

        current_v2 = (
            await session.execute(
                select(Tag.name)
                .join(IssueTag, IssueTag.tag_id == Tag.id)
                .where(IssueTag.issue_id == issue_id, IssueTag.removed_at.is_(None))
            )
        ).scalars().all()
        assert current_v2 == ["reverted"]

        actions_v2 = sorted(
            (
                await session.execute(
                    select(IssueTagHistory.action).where(IssueTagHistory.issue_id == issue_id)
                )
            ).scalars().all()
        )
        assert actions_v2 == ["added", "added", "removed"]

    await engine.dispose()
