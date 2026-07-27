"""Functional tests running the team's own "Engineering Points System" doc
worked examples through the real pipeline: normalizer upserts (seeding
issues + tags exactly like a Zoho sync would) -> app/jobs/score_points.py's
run_score_points() -> assert the resulting points_events ledger.

Requires a real Postgres reachable via DATABASE_URL (skipped otherwise).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text

from app.config import get_settings
from app.db import get_engine, get_sessionmaker
from app.db_partitions import ensure_partitions_around
from app.jobs.score_points import run_score_points
from app.models import Actor, Issue, PointsEvent, Project, Tag, Team, UnscoredTicket
from app.services import normalizer
from app.zoho.client import ZohoItem, ZohoProject, ZohoTag, ZohoTeam, ZohoUser

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="requires a live DATABASE_URL"
)

_TABLES_TO_RESET = (
    "points_unscored_tickets", "points_events",
    "issue_tag_history", "issue_tags", "issues", "tags", "projects", "actors", "teams",
    "sync_state",
)


def _item(item_id: str, *, owner: str, creator: str, tag_ids: list[str], closed: bool) -> ZohoItem:
    node = {
        "itemId": item_id,
        "itemName": f"Item {item_id}",
        "projectId": "proj-1",
        "ownerId": owner,
        "createdBy": creator,
        "statusId": "status-done" if closed else "status-open",
        "statusName": "Done" if closed else "Open",
        "createdTime": "2026-07-01T00:00:00Z",
        "updatedTime": "2026-07-01T00:00:00Z",
        "tags": [{"tagId": t} for t in tag_ids],
    }
    if closed:
        node["completedDate"] = "2026-07-02T00:00:00Z"
    return ZohoItem.from_node(node, project_id="proj-1")


async def _seed_common(session) -> None:
    await normalizer.upsert_zoho_teams(session, [ZohoTeam.from_node({"teamId": "team-1", "teamName": "Core"})])
    await normalizer.upsert_projects(
        session, [ZohoProject.from_node({"projectId": "proj-1", "projectName": "P1"}, team_id="team-1")]
    )
    await normalizer.upsert_zoho_actors(
        session,
        [
            ZohoUser.from_node({"zuid": "reporter-a", "name": "Aditi"}),
            ZohoUser.from_node({"zuid": "assignee-b", "name": "Rohan"}),
        ],
    )
    all_tags = [
        "type:bug-find", "type:bug-fix", "type:security", "type:perf", "triaged", "reverted",
        "rca-done", "own-code",
        "sev:critical", "sev:major", "sev:minor",
        "area:infra", "area:backend", "area:frontend", "area:design",
        "size:s", "size:m", "size:l",
    ]
    await normalizer.upsert_tags(
        session, [ZohoTag.from_node({"tagId": n, "tagName": n}, team_id="team-1") for n in all_tags]
    )


async def _seed_items(session, items: list[ZohoItem]) -> None:
    await normalizer.upsert_items(session, items)
    await normalizer.upsert_item_tags(session, items)


async def _awards_for(session, zoho_item_id: str) -> list[tuple[str, str, int]]:
    issue_id = (
        await session.execute(select(Issue.id).where(Issue.zoho_id == zoho_item_id))
    ).scalar_one()
    rows = (
        await session.execute(
            select(PointsEvent.event_kind, PointsEvent.category, PointsEvent.points)
            .where(PointsEvent.issue_id == issue_id)
            .order_by(PointsEvent.id)
        )
    ).all()
    return [tuple(r) for r in rows]


@pytest.fixture(autouse=True)
async def _reset_db():
    get_settings.cache_clear()
    engine = get_engine()
    async with engine.begin() as conn:
        await ensure_partitions_around(conn, datetime.now(UTC))
    Session = get_sessionmaker()
    async with Session() as session:
        async with session.begin():
            for table in _TABLES_TO_RESET:
                await session.execute(text(f"DELETE FROM {table}"))
    yield
    await engine.dispose()


@pytest.mark.asyncio
async def test_worked_example_1_critical_infra_bug_find_and_fix():
    Session = get_sessionmaker()
    async with Session() as session:
        async with session.begin():
            await _seed_common(session)
    async with Session() as session:
        async with session.begin():
            find = _item(
                "find-1", owner="assignee-b", creator="reporter-a", closed=False,
                tag_ids=["type:bug-find", "sev:critical", "area:infra", "triaged"],
            )
            fix = _item(
                "fix-1", owner="assignee-b", creator="reporter-a", closed=True,
                tag_ids=["type:bug-fix", "sev:critical", "area:infra", "triaged"],
            )
            await _seed_items(session, [find, fix])

    result = await run_score_points()
    assert result["scoring"]["awarded"] == 2

    async with Session() as session:
        assert await _awards_for(session, "find-1") == [("award", "bug_find", 5)]
        assert await _awards_for(session, "fix-1") == [("award", "bug_fix", 10)]

        reporter_id = (await session.execute(select(Actor.id).where(Actor.zoho_id == "reporter-a"))).scalar_one()
        assignee_id = (await session.execute(select(Actor.id).where(Actor.zoho_id == "assignee-b"))).scalar_one()
        find_actor = (
            await session.execute(
                select(PointsEvent.actor_id).join(Issue, Issue.id == PointsEvent.issue_id)
                .where(Issue.zoho_id == "find-1")
            )
        ).scalar_one()
        fix_actor = (
            await session.execute(
                select(PointsEvent.actor_id).join(Issue, Issue.id == PointsEvent.issue_id)
                .where(Issue.zoho_id == "fix-1")
            )
        ).scalar_one()
        assert find_actor == reporter_id  # find points -> reporter
        assert fix_actor == assignee_id  # fix points -> assignee


@pytest.mark.asyncio
async def test_worked_example_2_own_code_zeroes_find_points():
    Session = get_sessionmaker()
    async with Session() as session:
        async with session.begin():
            await _seed_common(session)
    async with Session() as session:
        async with session.begin():
            find = _item(
                "find-2", owner="reporter-a", creator="reporter-a", closed=False,
                tag_ids=["type:bug-find", "sev:minor", "area:frontend", "triaged", "own-code"],
            )
            fix = _item(
                "fix-2", owner="reporter-a", creator="reporter-a", closed=True,
                tag_ids=["type:bug-fix", "sev:minor", "area:frontend", "triaged"],
            )
            await _seed_items(session, [find, fix])

    await run_score_points()

    async with Session() as session:
        assert await _awards_for(session, "find-2") == [("award", "bug_find", 0)]
        assert await _awards_for(session, "fix-2") == [("award", "bug_fix", 1)]


@pytest.mark.asyncio
async def test_worked_example_6_only_current_severity_at_triage_counts():
    Session = get_sessionmaker()
    async with Session() as session:
        async with session.begin():
            await _seed_common(session)

    # Reporter initially tags only sev:critical (no area, no triaged yet).
    async with Session() as session:
        async with session.begin():
            find = _item(
                "find-6", owner="reporter-a", creator="reporter-a", closed=False,
                tag_ids=["type:bug-find", "sev:critical"],
            )
            await _seed_items(session, [find])

    result = await run_score_points()
    assert result["scoring"]["unscored"] == 1
    async with Session() as session:
        row = (
            await session.execute(
                select(UnscoredTicket.reason).join(Issue, Issue.id == UnscoredTicket.issue_id)
                .where(Issue.zoho_id == "find-6")
            )
        ).scalar_one()
        assert row == "missing_bug_fields"

    # Triage downgrades: sev:critical removed, sev:minor + area:design + triaged added.
    async with Session() as session:
        async with session.begin():
            find_triaged = _item(
                "find-6", owner="reporter-a", creator="reporter-a", closed=False,
                tag_ids=["type:bug-find", "sev:minor", "area:design", "triaged"],
            )
            await _seed_items(session, [find_triaged])

    await run_score_points()
    async with Session() as session:
        # design/minor find = 1 point, not whatever "critical" would have scored.
        assert await _awards_for(session, "find-6") == [("award", "bug_find", 1)]
        resolved = (
            await session.execute(
                select(UnscoredTicket.resolved_at).join(Issue, Issue.id == UnscoredTicket.issue_id)
                .where(Issue.zoho_id == "find-6")
            )
        ).scalar_one()
        assert resolved is not None


@pytest.mark.asyncio
async def test_worked_example_8_revert_nets_to_zero_without_erasing_history():
    Session = get_sessionmaker()
    async with Session() as session:
        async with session.begin():
            await _seed_common(session)
    async with Session() as session:
        async with session.begin():
            fix = _item(
                "fix-8", owner="assignee-b", creator="reporter-a", closed=True,
                tag_ids=["type:bug-fix", "sev:major", "area:backend", "triaged"],
            )
            await _seed_items(session, [fix])

    await run_score_points()
    async with Session() as session:
        assert await _awards_for(session, "fix-8") == [("award", "bug_fix", 4)]

    # 2 "days" later: reverted tag is added.
    async with Session() as session:
        async with session.begin():
            fix_reverted = _item(
                "fix-8", owner="assignee-b", creator="reporter-a", closed=True,
                tag_ids=["type:bug-fix", "sev:major", "area:backend", "triaged", "reverted"],
            )
            await _seed_items(session, [fix_reverted])

    result = await run_score_points()
    assert result["reverted"] == 1

    async with Session() as session:
        rows = await _awards_for(session, "fix-8")
        assert rows == [("award", "bug_fix", 4), ("reversal", "bug_fix", -4)]
        assert sum(points for _, _, points in rows) == 0  # nets to zero...
        assert len(rows) == 2  # ...but history is never erased


@pytest.mark.asyncio
async def test_multi_category_ticket_held_for_review_pending_confirmed_subscale():
    """Worked example #9 (security + perf on one ticket) exercises the
    per-category-independent resolution path, but this build deliberately
    does NOT auto-score security or perf (see points_rules.py / the plan's
    open questions: security's sub-severity scale and perf's before/after
    signal aren't confirmed) — both land in points_unscored_tickets rather
    than guessing a point value. This test asserts that conservative,
    intentional behavior, not the doc's raw "+15" outcome.
    """
    Session = get_sessionmaker()
    async with Session() as session:
        async with session.begin():
            await _seed_common(session)
    async with Session() as session:
        async with session.begin():
            ticket = _item(
                "sec-perf-9", owner="assignee-b", creator="reporter-a", closed=True,
                tag_ids=["type:security", "type:perf", "size:m", "triaged"],
            )
            await _seed_items(session, [ticket])

    result = await run_score_points()
    assert result["scoring"]["awarded"] == 0
    assert result["scoring"]["unscored"] == 1

    async with Session() as session:
        assert await _awards_for(session, "sec-perf-9") == []
        reason = (
            await session.execute(
                select(UnscoredTicket.reason).join(Issue, Issue.id == UnscoredTicket.issue_id)
                .where(Issue.zoho_id == "sec-perf-9")
            )
        ).scalar_one()
        assert reason == "needs_review"


@pytest.mark.asyncio
async def test_idempotent_rerun_does_not_double_award():
    Session = get_sessionmaker()
    async with Session() as session:
        async with session.begin():
            await _seed_common(session)
    async with Session() as session:
        async with session.begin():
            fix = _item(
                "fix-idem", owner="assignee-b", creator="reporter-a", closed=True,
                tag_ids=["type:bug-fix", "sev:minor", "area:backend", "triaged"],
            )
            await _seed_items(session, [fix])

    await run_score_points()
    await run_score_points()  # same window/state re-run

    async with Session() as session:
        assert await _awards_for(session, "fix-idem") == [("award", "bug_fix", 1)]
