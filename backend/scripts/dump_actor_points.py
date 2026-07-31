"""One-off diagnostic: dump the points_events ledger for a set of actors.

Not part of the app — invoked ad hoc via a throwaway workflow_dispatch job
to verify the live ledger against a hand-computed expectation. Safe to
delete; read-only.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.db import get_sessionmaker
from app.models import Actor, Issue, PointsEvent

TARGET_NAMES = ["Sachin", "shivansh-source"]


async def main() -> None:
    Session = get_sessionmaker()
    async with Session() as session:
        for name in TARGET_NAMES:
            actor_id = (
                await session.execute(select(Actor.id).where(Actor.name == name))
            ).scalar_one_or_none()
            print(f"\n=== {name} (actor_id={actor_id}) ===")
            if actor_id is None:
                print("  no matching actor row")
                continue

            rows = (
                await session.execute(
                    select(
                        Issue.identifier, PointsEvent.category, PointsEvent.event_kind,
                        PointsEvent.points, PointsEvent.effective_at, PointsEvent.rule_key,
                    )
                    .join(Issue, Issue.id == PointsEvent.issue_id)
                    .where(PointsEvent.actor_id == actor_id)
                    .order_by(PointsEvent.effective_at)
                )
            ).all()
            total = 0
            for identifier, category, kind, points, eff, rule_key in rows:
                total += points
                print(f"  {identifier:10s} {category:12s} {kind:8s} {points:+4d}  eff={eff}  rule={rule_key}")
            print(f"  ---- TOTAL (all time): {total} ----")


if __name__ == "__main__":
    asyncio.run(main())
