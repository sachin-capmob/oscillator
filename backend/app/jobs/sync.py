"""Cron sync entrypoint:  python -m app.jobs.sync

One run = pull from Linear and normalize into Postgres, then refresh rollups.

Watermark: last_synced_at in sync_state (key='linear'). NULL => full backfill.
Incremental runs use ``since = last_synced_at - 5 min`` (overlap so nothing is
missed between runs); the watermark advances to the run's start time (UTC) ONLY
after every phase succeeds. Any failure exits non-zero WITHOUT advancing the
watermark, so the next run safely re-syncs the same window (upserts are idempotent).
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db import get_engine, get_sessionmaker
from app.db_partitions import ensure_partitions_around
from app.linear.client import LinearClient
from app.models import SyncState
from app.services import normalizer

logger = logging.getLogger("app.sync")

WATERMARK_KEY = "linear"
OVERLAP = timedelta(minutes=5)


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


async def refresh_all_views(engine) -> list[str]:
    """REFRESH ... CONCURRENTLY every materialized view (autocommit, no txn)."""
    ac_engine = engine.execution_options(isolation_level="AUTOCOMMIT")
    async with ac_engine.connect() as conn:
        names = (
            await conn.execute(
                text(
                    "SELECT matviewname FROM pg_matviews "
                    "WHERE schemaname='public' ORDER BY matviewname"
                )
            )
        ).scalars().all()
        for name in names:
            logger.info("Refreshing materialized view %s", name)
            await conn.execute(text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {name}"))
    return list(names)


async def run_sync() -> dict:
    run_start = datetime.now(UTC)
    engine = get_engine()
    Session = get_sessionmaker()

    # Ensure current/adjacent monthly partitions for raw_events before landing.
    async with engine.begin() as conn:
        await ensure_partitions_around(conn, run_start)

    async with Session() as session:
        last = await _read_watermark(session)
    since = (last - OVERLAP) if last else None
    mode = "incremental" if since else "full backfill"
    logger.info("Sync start (%s); since=%s", mode, since.isoformat() if since else None)

    # --- pull from Linear ---
    async with LinearClient() as client:
        teams = await client.fetch_teams()
        users = await client.fetch_users()
        cycles = await client.fetch_cycles(since)
        issues = await client.fetch_issues(since)
        comments = await client.fetch_comments(since)
    pulled = {
        "teams": len(teams), "users": len(users), "cycles": len(cycles),
        "issues": len(issues), "comments": len(comments),
    }
    logger.info("Pulled: %s", pulled)

    # --- normalize (dependency order; commit per phase) ---
    counts: dict[str, int] = {}
    async with Session() as session:
        async with session.begin():
            counts["teams"] = await normalizer.upsert_teams(session, teams)
        async with session.begin():
            counts["actors"] = await normalizer.upsert_actors(session, users)
        async with session.begin():
            counts["cycles"] = await normalizer.upsert_cycles(session, cycles)
        async with session.begin():
            counts["issues"], counts["transitions"] = await normalizer.upsert_issues(
                session, issues
            )
        async with session.begin():
            counts["comments"] = await normalizer.upsert_comments(session, comments)
    logger.info("Upserted: %s", counts)

    # --- refresh rollups ---
    views = await refresh_all_views(engine)

    # --- advance watermark only after full success ---
    async with Session() as session:
        async with session.begin():
            await _write_watermark(session, run_start)
    logger.info("Watermark advanced to %s", run_start.isoformat())

    return {"mode": mode, "since": since, "watermark": run_start,
            "pulled": pulled, "upserted": counts, "views_refreshed": views}


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        result = asyncio.run(run_sync())
    except Exception:
        logger.exception("Sync FAILED")
        return 1
    print("\n=== SYNC SUMMARY ===")
    print(f"mode:       {result['mode']}")
    print(f"watermark:  {result['watermark'].isoformat()}")
    print(f"pulled:     {result['pulled']}")
    print(f"upserted:   {result['upserted']}")
    print(f"views:      {result['views_refreshed'] or '(none yet)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
