"""GET /api/insights/actor-issues now returns each issue's current labels
(the "Closed issues by person" panel on the People page renders them as
chips) — this proves the array_agg join in app/api/insights.py lines up
with the same issue_tags/tags tables the scoring engine reads.

Requires a live DATABASE_URL (skipped otherwise).
"""

from __future__ import annotations

import os

import httpx
import pytest

from app.config import get_settings
from app.db import get_engine, get_sessionmaker
from app.db_partitions import ensure_partitions_around
from app.linear.client import LinearIssue, LinearLabel, LinearTeam, LinearUser
from app.main import app
from app.services import normalizer

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="requires a live DATABASE_URL"
)

_TOKEN = "test-dashboard-token"


@pytest.fixture(autouse=True)
async def _setup():
    os.environ["DASHBOARD_AUTH_TOKEN"] = _TOKEN
    get_settings.cache_clear()
    from datetime import UTC, datetime

    from sqlalchemy import text

    engine = get_engine()
    async with engine.begin() as conn:
        await ensure_partitions_around(conn, datetime.now(UTC))
    Session = get_sessionmaker()
    async with Session() as session:
        async with session.begin():
            for table in ("issue_tags", "issues", "tags", "actors", "teams", "sync_state"):
                await session.execute(text(f"DELETE FROM {table}"))

    async with Session() as session:
        async with session.begin():
            await normalizer.upsert_teams(session, [LinearTeam.from_node({"id": "t1", "name": "Core"})])
    async with Session() as session:
        async with session.begin():
            await normalizer.upsert_actors(session, [LinearUser.from_node({"id": "u1", "name": "Ada"})])
    async with Session() as session:
        async with session.begin():
            await normalizer.upsert_labels(
                session,
                [
                    LinearLabel.from_node({"id": n, "name": n, "team": {"id": "t1"}})
                    for n in ("type:infra", "size:m")
                ],
            )
    async with Session() as session:
        async with session.begin():
            issue = LinearIssue.from_node(
                {
                    "id": "labeled-1", "title": "Migrate the thing", "team": {"id": "t1"},
                    "assignee": {"id": "u1"}, "creator": {"id": "u1"},
                    "state": {"name": "Done", "type": "completed"},
                    "createdAt": "2026-07-01T00:00:00Z", "completedAt": "2026-07-02T00:00:00Z",
                    "updatedAt": "2026-07-02T00:00:00Z",
                    "labels": {"nodes": [{"id": "type:infra"}, {"id": "size:m"}]},
                }
            )
            await normalizer.upsert_issues(session, [issue])
            await normalizer.upsert_issue_tags(session, [issue])

    yield
    await engine.dispose()


@pytest.mark.asyncio
async def test_actor_issues_includes_current_labels():
    Session = get_sessionmaker()
    async with Session() as session:
        from sqlalchemy import select

        from app.models import Actor

        actor_id = (
            await session.execute(select(Actor.id).where(Actor.linear_id == "u1"))
        ).scalar_one()

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/insights/actor-issues",
            params={"actor_id": actor_id, "range": "all"},
            headers={"Authorization": f"Bearer {_TOKEN}"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["issues"]) == 1
    assert body["issues"][0]["labels"] == ["size:m", "type:infra"]
