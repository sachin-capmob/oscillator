"""End-to-end test of the Engineering Points API against real seeded data
and the real scoring job — proves the router, schemas, and DB queries all
line up. Requires a live DATABASE_URL (skipped otherwise).

Uses httpx.ASGITransport (in-process, one event loop for the whole test) —
a plain TestClient/requests-style call here would exercise a NEW event loop
per request while the async DB engine's connection pool is bound to
whichever loop created it first; that's a test-harness mismatch, not a
production concern (a real ASGI server keeps one persistent loop).
"""

from __future__ import annotations

import os

import httpx
import pytest
from sqlalchemy import text

from app.config import get_settings
from app.db import get_engine
from app.jobs.score_points import run_score_points
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
    from app.db_partitions import ensure_partitions_around
    from app.db import get_sessionmaker
    from datetime import UTC, datetime

    engine = get_engine()
    async with engine.begin() as conn:
        await ensure_partitions_around(conn, datetime.now(UTC))
    Session = get_sessionmaker()
    async with Session() as session:
        async with session.begin():
            for table in (
                "points_unscored_tickets", "points_events", "issue_tag_history",
                "issue_tags", "issues", "tags", "actors", "teams", "sync_state",
            ):
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
                    for n in ("type:bug-fix", "sev:major", "area:backend", "triaged")
                ],
            )
    async with Session() as session:
        async with session.begin():
            issue = LinearIssue.from_node(
                {
                    "id": "fix-api-1", "title": "Fix the thing", "team": {"id": "t1"},
                    "assignee": {"id": "u1"}, "creator": {"id": "u1"},
                    "state": {"name": "Done", "type": "completed"},
                    "createdAt": "2026-07-01T00:00:00Z", "completedAt": "2026-07-02T00:00:00Z",
                    "updatedAt": "2026-07-02T00:00:00Z",
                    "labels": {"nodes": [{"id": n} for n in ("type:bug-fix", "sev:major", "area:backend", "triaged")]},
                }
            )
            await normalizer.upsert_issues(session, [issue])
            await normalizer.upsert_issue_tags(session, [issue])

    await run_score_points()
    yield
    await engine.dispose()


@pytest.mark.asyncio
async def test_points_by_actor_reflects_scored_ledger():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/insights/points/by-actor", params={"range": "all"},
            headers={"Authorization": f"Bearer {_TOKEN}"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["actors"]) == 1
    actor = body["actors"][0]
    assert actor["name"] == "Ada"
    assert actor["total_points"] == 4
    assert actor["by_category"] == [{"category": "bug_fix", "points": 4}]


@pytest.mark.asyncio
async def test_points_ledger_returns_the_award_row():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/insights/points/ledger", params={"range": "all"},
            headers={"Authorization": f"Bearer {_TOKEN}"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    entry = body["entries"][0]
    assert entry["category"] == "bug_fix"
    assert entry["event_kind"] == "award"
    assert entry["points"] == 4
    assert entry["identifier"] is None or isinstance(entry["identifier"], str)


@pytest.mark.asyncio
async def test_unscored_endpoint_empty_when_everything_resolved():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/insights/points/unscored", headers={"Authorization": f"Bearer {_TOKEN}"}
        )
    assert resp.status_code == 200
    assert resp.json()["tickets"] == []


@pytest.mark.asyncio
async def test_requires_bearer_token():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/insights/points/by-actor")
    assert resp.status_code == 401
