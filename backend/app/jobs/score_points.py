"""Cron scoring entrypoint:  python -m app.jobs.score_points

Reads labels off Linear issues and applies the Engineering Points tables
(app/models/points_rules.py) to produce an append-only ledger
(points_events). Mirrors app/jobs/sync.py's watermark-in-sync_state pattern
(key='points') but is NOT a straight port of that skeleton, because points
can be awarded, then later reversed (a revert) or bonused (an RCA writeup)
by a label added long after the original scoring run — see
app/models/points.py for why this can't be a stateless recompute.

One run does two independent things over the SAME watermark window:

1. SCORE new candidates — closed tickets, tickets whose `triaged` label was
   just added, and any ticket still sitting unresolved in
   points_unscored_tickets (retried every run, since a label fix can land
   any time). Every category on a ticket is resolved independently:
     - bug_find / bug_fix unlock once `triaged` is present, REGARDLESS of
       whether the ticket itself is closed (a bug report can sit "accepted,
       being fixed" for a while — the doc's own rule is "triaged is the
       signal", not "closed is the signal", for find/fix specifically).
     - every other category only scores once the ticket is actually closed
       ("points award on merge and deploy, not on PR open").
   A ticket with an unresolvable category (missing labels, needs a signal
   the label scheme can't express yet) is upserted into
   points_unscored_tickets rather than silently skipped or guessed.

2. ADJUST existing awards — a newly-added `reverted` label reverses every
   un-reversed award on that ticket (a new `reversal` row, `points` negated,
   pointing back at the original via `reverses_event_id` — the original row
   is never mutated); a newly-added `rca-done` label adds a `+4` `bonus` row
   on top of the ticket's `incident` award. Both are read from
   issue_tag_history (the append-only label diff log Linear ingestion
   writes — see app/services/normalizer.py's upsert_issue_tags), the same
   way this file discovers newly-triaged tickets.

Idempotent throughout: award/reversal/bonus inserts are guarded by the
partial-unique indexes on points_events (see app/models/points.py), so
re-running over the same window is always safe.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db import get_sessionmaker
from app.models import Issue, IssueTag, IssueTagHistory, PointsEvent, SyncState, Tag, UnscoredTicket
from app.models.points_rules import (
    AREA_LABELS,
    BUG_CATEGORIES,
    BUG_POINTS,
    FLAT_POINTS,
    OWN_CODE_TAG,
    RCA_DONE_TAG,
    REVERTED_TAG,
    RULES_VERSION,
    SEVERITY_LABELS,
    SIZE_LABELS,
    SIZED_CATEGORIES,
    SIZED_POINTS,
    TRIAGED_TAG,
    TYPE_TAG_TO_CATEGORY,
)

logger = logging.getLogger("app.score_points")

WATERMARK_KEY = "points"
OVERLAP = timedelta(hours=2)
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

# Categories that need a signal the current label scheme can't express yet
# (security's sub-severity scale, perf's before/after number, copy/docs'
# small-vs-large split) — always held for manual review, never auto-scored.
# See points_rules.py and the plan's open questions.
_NEEDS_REVIEW_CATEGORIES = {"security", "perf", "copy", "docs"}

# Any tag whose ADDITION should make an issue a scoring candidate again
# (see _gather_candidates) — every tag _resolve_categories actually reads.
_RELEVANT_CANDIDATE_TAGS = (
    set(TYPE_TAG_TO_CATEGORY.keys())
    | set(SEVERITY_LABELS.keys())
    | set(AREA_LABELS.keys())
    | set(SIZE_LABELS.keys())
    | {TRIAGED_TAG, OWN_CODE_TAG}
)


async def _read_watermark(session) -> datetime | None:
    res = await session.execute(
        select(SyncState.last_synced_at).where(SyncState.key == WATERMARK_KEY)
    )
    return res.scalar_one_or_none()


async def _write_watermark(session, ts: datetime) -> None:
    stmt = pg_insert(SyncState).values(key=WATERMARK_KEY, last_synced_at=ts)
    stmt = stmt.on_conflict_do_update(index_elements=[SyncState.key], set_={"last_synced_at": ts})
    await session.execute(stmt)


def _resolve_categories(
    tag_names: set[str], *, is_closed: bool
) -> tuple[list[dict], list[str]]:
    """One issue's current tags -> (resolvable score entries, blocking reasons).

    Each entry: {"category", "points", "rule_key"}. Every recognized type:*
    tag on the ticket is resolved independently (a ticket can carry more
    than one, e.g. type:security + type:perf — see worked example #9 in the
    scoring doc), so the return value can have MULTIPLE resolved entries
    and/or multiple blocking reasons for the same ticket simultaneously.
    """
    type_tags = [t for t in tag_names if t in TYPE_TAG_TO_CATEGORY]
    if not type_tags:
        return [], ["missing_type"]

    sev = next((SEVERITY_LABELS[t] for t in tag_names if t in SEVERITY_LABELS), None)
    area = next((AREA_LABELS[t] for t in tag_names if t in AREA_LABELS), None)
    size = next((SIZE_LABELS[t] for t in tag_names if t in SIZE_LABELS), None)
    triaged = TRIAGED_TAG in tag_names

    resolved: list[dict] = []
    reasons: list[str] = []

    for type_tag in type_tags:
        category = TYPE_TAG_TO_CATEGORY[type_tag]

        if category in BUG_CATEGORIES:
            # Bug find/fix unlock on TRIAGE, not on ticket closure.
            if sev is None or area is None:
                reasons.append("missing_bug_fields")
                continue
            if not triaged:
                reasons.append("awaiting_triage")
                continue
            find_pts, fix_pts = BUG_POINTS[area][sev]
            pts = find_pts if category == "bug_find" else fix_pts
            if category == "bug_find" and OWN_CODE_TAG in tag_names:
                pts = 0  # own-code rule: fix points still apply, find points zeroed
            resolved.append(
                {"category": category, "points": pts, "rule_key": f"{category}:{area}:{sev}"}
            )
            continue

        # Every other category scores on ticket CLOSE, not on triage.
        if not is_closed:
            reasons.append("awaiting_close")
            continue

        if category in _NEEDS_REVIEW_CATEGORIES:
            reasons.append("needs_review")
            continue

        if category in SIZED_CATEGORIES:
            if size is None:
                reasons.append("missing_size")
                continue
            pts = SIZED_POINTS[category][size]
            resolved.append({"category": category, "points": pts, "rule_key": f"{category}:size:{size}"})
            continue

        pts = FLAT_POINTS.get(category)
        if pts is None:
            reasons.append("missing_type")
            continue
        resolved.append({"category": category, "points": pts, "rule_key": f"flat:{category}"})

    return resolved, reasons


async def _gather_candidates(session, since: datetime) -> set[int]:
    newly_closed = (
        await session.execute(
            text(
                """
                SELECT id FROM issues
                WHERE state_type IN ('completed', 'canceled')
                  AND coalesce(completed_at, canceled_at) >= :since
                """
            ),
            {"since": since},
        )
    ).scalars().all()

    pending_retry = (
        await session.execute(select(UnscoredTicket.issue_id).where(UnscoredTicket.resolved_at.is_(None)))
    ).scalars().all()

    # Any tag relevant to resolution (a type:*, triaged, sev:*, area:*,
    # size:*, or own-code add) makes an issue worth re-evaluating — not just
    # `triaged` specifically. Otherwise a bug ticket tagged type:bug-find
    # with no area/severity yet, and no triaged tag, would never become a
    # candidate at all and so would never show up as "unscored" — it would
    # just be silently invisible instead of surfacing the missing labels.
    newly_relevant_tagged = (
        await session.execute(
            select(IssueTagHistory.issue_id)
            .join(Tag, Tag.id == IssueTagHistory.tag_id)
            .where(
                Tag.name.in_(_RELEVANT_CANDIDATE_TAGS),
                IssueTagHistory.action == "added",
                IssueTagHistory.changed_at >= since,
            )
        )
    ).scalars().all()

    return set(newly_closed) | set(pending_retry) | set(newly_relevant_tagged)


async def _score_candidates(session, candidate_ids: set[int]) -> dict:
    if not candidate_ids:
        return {"candidates": 0, "awarded": 0, "unscored": 0, "resolved": 0}

    issue_rows = (
        await session.execute(
            select(
                Issue.id, Issue.creator_id, Issue.assignee_id, Issue.state_type,
                Issue.completed_at, Issue.canceled_at,
            ).where(Issue.id.in_(candidate_ids))
        )
    ).all()

    tag_rows = (
        await session.execute(
            select(IssueTag.issue_id, Tag.name)
            .join(Tag, Tag.id == IssueTag.tag_id)
            .where(IssueTag.issue_id.in_(candidate_ids), IssueTag.removed_at.is_(None))
        )
    ).all()
    tags_by_issue: dict[int, set[str]] = {}
    for issue_id, name in tag_rows:
        tags_by_issue.setdefault(issue_id, set()).add(name)

    awarded_rows = (
        await session.execute(
            select(PointsEvent.issue_id, PointsEvent.category)
            .where(PointsEvent.issue_id.in_(candidate_ids), PointsEvent.event_kind == "award")
        )
    ).all()
    awarded_categories: dict[int, set[str]] = {}
    for issue_id, category in awarded_rows:
        awarded_categories.setdefault(issue_id, set()).add(category)

    pending_retry_ids = set(
        (
            await session.execute(
                select(UnscoredTicket.issue_id).where(UnscoredTicket.resolved_at.is_(None))
            )
        ).scalars().all()
    )

    award_rows: list[dict] = []
    unscored_upserts: list[dict] = []
    resolved_ids: list[int] = []

    for issue_id, creator_id, assignee_id, state_type, completed_at, canceled_at in issue_rows:
        tag_names = tags_by_issue.get(issue_id, set())
        is_closed = state_type in ("completed", "canceled")
        resolved, reasons = _resolve_categories(tag_names, is_closed=is_closed)
        already = awarded_categories.get(issue_id, set())
        effective_at = completed_at or canceled_at or datetime.now(UTC)

        for entry in resolved:
            if entry["category"] in already:
                continue  # scored on a prior run
            actor_id = creator_id if entry["category"] == "bug_find" else assignee_id
            award_rows.append(
                {
                    "issue_id": issue_id,
                    "actor_id": actor_id,
                    "category": entry["category"],
                    "event_kind": "award",
                    "points": entry["points"],
                    "rule_key": entry["rule_key"],
                    "rules_version": RULES_VERSION,
                    "label_state": sorted(tag_names),
                    "effective_at": effective_at,
                }
            )

        if reasons:
            unscored_upserts.append(
                {"issue_id": issue_id, "reason": reasons[0], "assignee_id": assignee_id}
            )
        elif issue_id in pending_retry_ids:
            resolved_ids.append(issue_id)

    if award_rows:
        stmt = pg_insert(PointsEvent).values(award_rows)
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["issue_id", "category"], index_where=text("event_kind = 'award'")
        )
        await session.execute(stmt)

    if unscored_upserts:
        stmt = pg_insert(UnscoredTicket).values(unscored_upserts)
        stmt = stmt.on_conflict_do_update(
            index_elements=[UnscoredTicket.issue_id],
            set_={
                "reason": stmt.excluded.reason,
                "assignee_id": stmt.excluded.assignee_id,
                "last_checked_at": text("now()"),
                "resolved_at": None,
            },
        )
        await session.execute(stmt)

    if resolved_ids:
        await session.execute(
            UnscoredTicket.__table__.update()
            .where(UnscoredTicket.issue_id.in_(resolved_ids))
            .values(resolved_at=text("now()"))
        )

    return {
        "candidates": len(candidate_ids),
        "awarded": len(award_rows),
        "unscored": len(unscored_upserts),
        "resolved": len(resolved_ids),
    }


async def _apply_reverts(session, since: datetime) -> int:
    events = (
        await session.execute(
            select(IssueTagHistory.issue_id, IssueTagHistory.changed_at)
            .join(Tag, Tag.id == IssueTagHistory.tag_id)
            .where(
                Tag.name == REVERTED_TAG,
                IssueTagHistory.action == "added",
                IssueTagHistory.changed_at >= since,
            )
        )
    ).all()
    if not events:
        return 0
    issue_ids = [e[0] for e in events]
    changed_at_by_issue = dict(events)

    prior_awards = (
        await session.execute(
            select(PointsEvent.id, PointsEvent.issue_id, PointsEvent.actor_id, PointsEvent.category, PointsEvent.points)
            .where(PointsEvent.issue_id.in_(issue_ids), PointsEvent.event_kind == "award")
        )
    ).all()
    already_reversed = set(
        (
            await session.execute(
                select(PointsEvent.reverses_event_id).where(PointsEvent.event_kind == "reversal")
            )
        ).scalars().all()
    )

    rows = [
        {
            "issue_id": issue_id,
            "actor_id": actor_id,
            "category": category,
            "event_kind": "reversal",
            "points": -points,
            "rule_key": f"reversal:{category}",
            "rules_version": RULES_VERSION,
            "reverses_event_id": event_id,
            "effective_at": changed_at_by_issue.get(issue_id, datetime.now(UTC)),
        }
        for event_id, issue_id, actor_id, category, points in prior_awards
        if event_id not in already_reversed
    ]
    if not rows:
        return 0
    stmt = pg_insert(PointsEvent).values(rows)
    stmt = stmt.on_conflict_do_nothing(
        index_elements=["reverses_event_id"], index_where=text("event_kind = 'reversal'")
    )
    await session.execute(stmt)
    return len(rows)


async def _apply_rca_bonuses(session, since: datetime) -> int:
    events = (
        await session.execute(
            select(IssueTagHistory.issue_id, IssueTagHistory.changed_at)
            .join(Tag, Tag.id == IssueTagHistory.tag_id)
            .where(
                Tag.name == RCA_DONE_TAG,
                IssueTagHistory.action == "added",
                IssueTagHistory.changed_at >= since,
            )
        )
    ).all()
    if not events:
        return 0
    issue_ids = [e[0] for e in events]
    changed_at_by_issue = dict(events)

    incident_awards = (
        await session.execute(
            select(PointsEvent.id, PointsEvent.issue_id, PointsEvent.actor_id)
            .where(
                PointsEvent.issue_id.in_(issue_ids),
                PointsEvent.category == "incident",
                PointsEvent.event_kind == "award",
            )
        )
    ).all()
    already_bonused = set(
        (
            await session.execute(
                select(PointsEvent.related_event_id).where(PointsEvent.event_kind == "bonus")
            )
        ).scalars().all()
    )

    rows = [
        {
            "issue_id": issue_id,
            "actor_id": actor_id,
            "category": "incident",
            "event_kind": "bonus",
            "points": FLAT_POINTS["incident_rca_bonus"],
            "rule_key": "incident_rca_bonus",
            "rules_version": RULES_VERSION,
            "related_event_id": event_id,
            "effective_at": changed_at_by_issue.get(issue_id, datetime.now(UTC)),
        }
        for event_id, issue_id, actor_id in incident_awards
        if event_id not in already_bonused
    ]
    if not rows:
        return 0
    stmt = pg_insert(PointsEvent).values(rows)
    stmt = stmt.on_conflict_do_nothing(
        index_elements=["related_event_id"], index_where=text("event_kind = 'bonus'")
    )
    await session.execute(stmt)
    return len(rows)


async def notify_unscored(session) -> int:
    """Extension point for a future Slack ping.

    Logs every not-yet-notified unscored ticket and marks it notified so a
    steady-state row doesn't re-log every run. Wiring this to Slack later is
    a matter of replacing the `logger.info` call below with a webhook POST —
    nothing about the scoring logic above needs to change.
    """
    rows = (
        await session.execute(
            select(UnscoredTicket.issue_id, UnscoredTicket.reason, UnscoredTicket.assignee_id)
            .where(UnscoredTicket.notified_at.is_(None), UnscoredTicket.resolved_at.is_(None))
        )
    ).all()
    if not rows:
        return 0
    for issue_id, reason, assignee_id in rows:
        logger.info(
            "Unscored ticket issue_id=%s reason=%s assignee_id=%s (Slack ping not wired up yet)",
            issue_id, reason, assignee_id,
        )
    await session.execute(
        UnscoredTicket.__table__.update()
        .where(UnscoredTicket.issue_id.in_([r[0] for r in rows]))
        .values(notified_at=text("now()"))
    )
    return len(rows)


async def run_score_points() -> dict:
    run_start = datetime.now(UTC)
    Session = get_sessionmaker()

    async with Session() as session:
        last = await _read_watermark(session)
    since = (last - OVERLAP) if last else _EPOCH
    mode = "incremental" if last else "full backfill"
    logger.info("Points scoring start (%s); since=%s", mode, since.isoformat())

    async with Session() as session:
        async with session.begin():
            candidates = await _gather_candidates(session, since)
            scoring = await _score_candidates(session, candidates)

    async with Session() as session:
        async with session.begin():
            n_reverted = await _apply_reverts(session, since)
        async with session.begin():
            n_bonused = await _apply_rca_bonuses(session, since)

    async with Session() as session:
        async with session.begin():
            n_notified = await notify_unscored(session)

    async with Session() as session:
        async with session.begin():
            await _write_watermark(session, run_start)
    logger.info("Points watermark advanced to %s", run_start.isoformat())

    return {
        "mode": mode,
        "since": since,
        "watermark": run_start,
        "scoring": scoring,
        "reverted": n_reverted,
        "rca_bonused": n_bonused,
        "notified": n_notified,
    }


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    try:
        result = asyncio.run(run_score_points())
    except Exception:
        logger.exception("Points scoring FAILED")
        return 1
    print("\n=== POINTS SCORING SUMMARY ===")
    print(f"mode:       {result['mode']}")
    print(f"watermark:  {result['watermark'].isoformat()}")
    print(f"scoring:    {result['scoring']}")
    print(f"reverted:   {result['reverted']}")
    print(f"rca_bonused: {result['rca_bonused']}")
    print(f"notified:   {result['notified']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
