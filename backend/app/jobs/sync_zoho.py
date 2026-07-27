"""Cron sync entrypoint:  python -m app.jobs.sync_zoho

Structurally mirrors app/jobs/sync.py (Linear): same watermark-in-sync_state
pattern, same phased-transaction / refresh-views / non-fatal-analytics
skeleton — against Zoho Sprints instead. Two differences Zoho's API forces:

* Every request is paced by ZohoSprintsClient's internal rate limiter
  (~28 calls/min, vs. Linear's much looser budget) — see app/zoho/client.py.
* Per-item COMMENTS are deliberately NOT ingested in this v1. Zoho Sprints
  has no bulk comment endpoint (one call per item), which at scale would
  either blow the rate-limit budget on a full backfill or need a resumable
  multi-run cursor to fetch safely. Nothing in the Engineering Points scoring
  engine reads comment bodies (it reads TAGS, not comment content — even the
  RCA bonus triggers off the `rca-done` tag, not comment text), so this is a
  scoped, visible limitation, not a silent gap: Zoho-sourced actors show 0
  comments until a follow-up paces per-item comment backfill.

Everything else (teams, projects, users, sprints, epics, tags, items, and
each item's current tag set) is re-pulled and idempotently upserted in full
on every run. Items/tags/etc. are cheap to paginate (no per-item calls), so
"only pull what changed since the watermark" isn't worth the bookkeeping
complexity here — Postgres upserts make re-processing the same row a no-op,
exactly the same reasoning Linear's own sync already relies on for
teams/users (fetched in full every run, no `since` filter, in sync.py).

Watermark: last_synced_at in sync_state (key='zoho'). Advances only after
every phase below succeeds, same all-or-nothing safety net as sync.py.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db import get_engine, get_sessionmaker
from app.db_partitions import ensure_partitions_around
from app.jobs.sync import refresh_all_views
from app.models import SyncState
from app.services import normalizer
from app.services.anomaly import detect_anomalies
from app.services.digest import generate_digests
from app.zoho.client import ZohoSprintsClient

logger = logging.getLogger("app.sync_zoho")

WATERMARK_KEY = "zoho"


async def _read_watermark(session) -> datetime | None:
    res = await session.execute(
        select(SyncState.last_synced_at).where(SyncState.key == WATERMARK_KEY)
    )
    return res.scalar_one_or_none()


async def _write_watermark(session, ts: datetime) -> None:
    stmt = pg_insert(SyncState).values(key=WATERMARK_KEY, last_synced_at=ts)
    stmt = stmt.on_conflict_do_update(
        index_elements=[SyncState.key], set_={"last_synced_at": ts}
    )
    await session.execute(stmt)


async def run_zoho_sync() -> dict:
    run_start = datetime.now(UTC)
    engine = get_engine()
    Session = get_sessionmaker()

    async with engine.begin() as conn:
        await ensure_partitions_around(conn, run_start)

    async with Session() as session:
        last = await _read_watermark(session)
    mode = "incremental" if last else "full backfill"
    logger.info("Zoho sync start (%s); previous watermark=%s", mode, last.isoformat() if last else None)

    # --- pull from Zoho Sprints ---
    async with ZohoSprintsClient() as client:
        teams = await client.fetch_teams()
        tags = await client.fetch_tags()

        projects = []
        for t in teams:
            projects.extend(await client.fetch_projects(team_id=t.id))
        # Fall back to the configured team if the workspace listing is empty
        # (some accounts only expose the single team the token is scoped to).
        if not projects:
            projects = await client.fetch_projects(team_id=client.team_id)

        users, sprints, epics, items = [], [], [], []
        seen_user_ids: set[str] = set()
        for p in projects:
            for u in await client.fetch_project_users(p.id, team_id=p.team_id):
                if u.id not in seen_user_ids:
                    seen_user_ids.add(u.id)
                    users.append(u)
            sprints.extend(await client.fetch_sprints(p.id, team_id=p.team_id))
            epics.extend(await client.fetch_epics(p.id, team_id=p.team_id))
            items.extend(await client.fetch_items(p.id, team_id=p.team_id))

    pulled = {
        "teams": len(teams), "projects": len(projects), "users": len(users),
        "tags": len(tags), "sprints": len(sprints), "epics": len(epics), "items": len(items),
    }
    logger.info("Pulled: %s", pulled)

    # --- normalize (dependency order; commit per phase) ---
    counts: dict[str, int] = {}
    async with Session() as session:
        async with session.begin():
            counts["teams"] = await normalizer.upsert_zoho_teams(session, teams)
        async with session.begin():
            counts["projects"] = await normalizer.upsert_projects(session, projects)
        async with session.begin():
            counts["actors"] = await normalizer.upsert_zoho_actors(session, users)
        async with session.begin():
            counts["tags"] = await normalizer.upsert_tags(session, tags)
        async with session.begin():
            counts["sprints"] = await normalizer.upsert_zoho_sprints(session, sprints)
        async with session.begin():
            counts["epics"] = await normalizer.upsert_epics(session, epics)
        async with session.begin():
            counts["items"], counts["transitions"] = await normalizer.upsert_items(session, items)
        async with session.begin():
            counts["issue_tags"], counts["tag_history"] = await normalizer.upsert_item_tags(
                session, items
            )
    logger.info("Upserted: %s", counts)

    # --- refresh rollups ---
    views = await refresh_all_views(engine)

    # --- derived analytics: anomaly flags + narrative digest ---
    # Same best-effort wrapping as sync.py — never fail the sync or block the
    # watermark over an analytics/LLM hiccup.
    analytics: dict[str, int] = {"anomalies": 0, "digests": 0}
    try:
        async with Session() as session:
            async with session.begin():
                analytics["anomalies"] = await detect_anomalies(session)
            async with session.begin():
                analytics["digests"] = await generate_digests(session, anchor=run_start.date())
    except Exception:  # noqa: BLE001 — analytics is non-critical to ingestion
        logger.exception("Derived analytics failed (non-fatal)")

    # --- advance watermark only after full success ---
    async with Session() as session:
        async with session.begin():
            await _write_watermark(session, run_start)
    logger.info("Zoho watermark advanced to %s", run_start.isoformat())

    return {
        "mode": mode, "watermark": run_start, "pulled": pulled,
        "upserted": counts, "views_refreshed": views, "analytics": analytics,
    }


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    try:
        result = asyncio.run(run_zoho_sync())
    except Exception:
        logger.exception("Zoho sync FAILED")
        return 1
    print("\n=== ZOHO SYNC SUMMARY ===")
    print(f"mode:       {result['mode']}")
    print(f"watermark:  {result['watermark'].isoformat()}")
    print(f"pulled:     {result['pulled']}")
    print(f"upserted:   {result['upserted']}")
    print(f"views:      {result['views_refreshed'] or '(none yet)'}")
    print(f"analytics:  {result['analytics']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
