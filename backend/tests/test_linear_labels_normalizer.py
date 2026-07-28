"""Functional tests for Linear label ingestion, especially tag diffing
(upsert_issue_tags) — the one genuinely new idiom this feature adds
(everything else mirrors upsert_issues/_write_transitions exactly).

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
from app.linear.client import LinearIssue, LinearLabel, LinearTeam, LinearUser
from app.models import Issue, IssueTag, IssueTagHistory, Tag
from app.services import normalizer

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="requires a live DATABASE_URL"
)


def _issue(issue_id: str, *, label_ids: list[str], status_type: str = "unstarted") -> LinearIssue:
    return LinearIssue.from_node(
        {
            "id": issue_id,
            "title": f"Issue {issue_id}",
            "team": {"id": "team-1"},
            "assignee": {"id": "user-1"},
            "creator": {"id": "user-1"},
            "state": {"name": status_type.capitalize(), "type": status_type},
            "createdAt": "2026-07-01T00:00:00Z",
            "updatedAt": "2026-07-01T00:00:00Z",
            "labels": {"nodes": [{"id": lid} for lid in label_ids]},
        }
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
                "issue_tag_history", "issue_tags", "issues", "tags", "actors", "teams",
            ):
                await session.execute(text(f"DELETE FROM {table}"))

    async with Session() as session:
        async with session.begin():
            await normalizer.upsert_teams(session, [LinearTeam.from_node({"id": "team-1", "name": "Core"})])
    async with Session() as session:
        async with session.begin():
            await normalizer.upsert_actors(session, [LinearUser.from_node({"id": "user-1", "name": "Ada"})])
    async with Session() as session:
        async with session.begin():
            await normalizer.upsert_labels(
                session,
                [
                    LinearLabel.from_node({"id": "tag-triaged", "name": "triaged", "team": {"id": "team-1"}}),
                    LinearLabel.from_node({"id": "tag-reverted", "name": "reverted", "team": {"id": "team-1"}}),
                ],
            )

    # --- sync run 1: issue carries only "triaged" ---
    issues = [_issue("issue-1", label_ids=["tag-triaged"])]
    async with Session() as session:
        async with session.begin():
            await normalizer.upsert_issues(session, issues)
    async with Session() as session:
        async with session.begin():
            n_touched, n_hist = await normalizer.upsert_issue_tags(session, issues)
        assert n_touched == 1
        assert n_hist == 1

        issue_id = (
            await session.execute(select(Issue.id).where(Issue.linear_id == "issue-1"))
        ).scalar_one()
        tag_id = (
            await session.execute(select(Tag.id).where(Tag.linear_id == "tag-triaged"))
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

    # --- sync run 2: SAME label state — must be a no-op (idempotent) ---
    async with Session() as session:
        async with session.begin():
            n_touched, n_hist = await normalizer.upsert_issue_tags(session, issues)
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
    issues_v2 = [_issue("issue-1", label_ids=["tag-reverted"])]
    async with Session() as session:
        async with session.begin():
            n_touched, n_hist = await normalizer.upsert_issue_tags(session, issues_v2)
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
