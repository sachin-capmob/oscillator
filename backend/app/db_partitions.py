"""Monthly partition management for raw_events and issue_history.

Both tables are declared ``PARTITION BY RANGE`` but the first migration creates
NO child partitions (migrations stay deterministic — no dependence on "now").
Instead partitions are created on demand here, always *before* rows for that
month are inserted:

  * app startup (lifespan)  -> ensure_partitions_around(now)  [current ± 1 month]
  * backfill job            -> ensure_partitions_for_range(...) over the data window
  * nightly scheduler       -> ensure_partitions_around(now)   [pre-creates next month]

Because we always ensure-before-insert, there is no DEFAULT partition and
``CREATE TABLE IF NOT EXISTS ... PARTITION OF`` can never conflict.
"""

from __future__ import annotations

from datetime import UTC, datetime

from dateutil.relativedelta import relativedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

# Tables declared PARTITION BY RANGE on a monthly timestamp column.
PARTITIONED_TABLES: dict[str, str] = {
    "raw_events": "received_at",
    "issue_history": "changed_at",
}


def _month_start(dt: datetime) -> datetime:
    return datetime(dt.year, dt.month, 1, tzinfo=UTC)


def _partition_name(table: str, month_start: datetime) -> str:
    return f"{table}_y{month_start.year:04d}m{month_start.month:02d}"


async def ensure_month_partition(
    conn: AsyncConnection, table: str, dt: datetime
) -> str:
    """Create (if absent) the monthly partition covering ``dt``. Returns its name."""
    if table not in PARTITIONED_TABLES:
        raise ValueError(f"{table!r} is not a partitioned table")
    start = _month_start(dt)
    end = start + relativedelta(months=1)
    name = _partition_name(table, start)
    # Bounds are inclusive-exclusive; pin to UTC so timestamptz comparison is unambiguous.
    await conn.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {name} PARTITION OF {table} "
            f"FOR VALUES FROM ('{start.isoformat()}') TO ('{end.isoformat()}')"
        )
    )
    return name


async def ensure_partitions_around(
    conn: AsyncConnection,
    now: datetime,
    months_back: int = 1,
    months_ahead: int = 1,
) -> list[str]:
    """Ensure partitions for [now - months_back, now + months_ahead] on all partitioned tables."""
    created: list[str] = []
    for table in PARTITIONED_TABLES:
        for offset in range(-months_back, months_ahead + 1):
            created.append(
                await ensure_month_partition(conn, table, now + relativedelta(months=offset))
            )
    return created


async def ensure_partitions_for_range(
    conn: AsyncConnection, table: str, start: datetime, end: datetime
) -> list[str]:
    """Ensure every monthly partition between ``start`` and ``end`` (inclusive)."""
    created: list[str] = []
    cursor = _month_start(start)
    last = _month_start(end)
    while cursor <= last:
        created.append(await ensure_month_partition(conn, table, cursor))
        cursor += relativedelta(months=1)
    return created
