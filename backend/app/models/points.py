"""The Engineering Points ledger (see app/jobs/score_points.py).

points_events is an append-only ledger: an `award` row is written when a
closed ticket is first scored, and later label changes on that SAME ticket
(a `reverted` or `rca-done` tag) produce a NEW `reversal`/`bonus` row rather
than mutating the original — so "what did the dashboard show as of date X"
and "what's the current net total" are both derivable and neither rewrites
history. This mirrors IssueHistory's never-mutate-prior-rows behavior.

points_unscored_tickets tracks closed tickets the scoring job could not
resolve (missing/ambiguous labels, awaiting triage/close, needs manual
review) — the seam where a Slack ping would eventually attach (see
app.jobs.score_points.notify_unscored, currently a no-op).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import TimestampMixin


class PointsEvent(Base, TimestampMixin):
    __tablename__ = "points_events"
    __table_args__ = (
        Index("ix_points_events_issue_id", "issue_id"),
        Index("ix_points_events_actor_id", "actor_id"),
        Index("ix_points_events_category", "category"),
        Index("ix_points_events_effective_at", "effective_at"),
        # One award per (ticket, category) — blocks double-award on re-run
        # while still allowing multiple categories on the same ticket (a
        # ticket tagged both type:security and type:perf gets two rows).
        Index(
            "uq_points_events_award_per_category",
            "issue_id",
            "category",
            unique=True,
            postgresql_where=text("event_kind = 'award'"),
        ),
        # A given award can be reversed / given a bonus at most once.
        Index(
            "uq_points_events_reverses_once",
            "reverses_event_id",
            unique=True,
            postgresql_where=text("event_kind = 'reversal'"),
        ),
        Index(
            "uq_points_events_bonus_once",
            "related_event_id",
            unique=True,
            postgresql_where=text("event_kind = 'bonus'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    issue_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("issues.id", ondelete="CASCADE"), nullable=False
    )
    # Who is credited/debited: reporter (find), assignee (fix/feature/incident),
    # or the reviewer (owner of the separate type:review ticket).
    actor_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("actors.id", ondelete="SET NULL")
    )
    # bug_find | bug_fix | feature_be | feature_fe | infra | design | chore |
    # perf | review | spike | ops_save | incident | security | ux | analytics
    # | copy | a11y | docs
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    # 'award' (normal scoring) | 'reversal' (revert clawback) | 'bonus' (RCA +4)
    event_kind: Mapped[str] = mapped_column(String(16), nullable=False, server_default="award")
    points: Mapped[int] = mapped_column(Integer, nullable=False)  # signed
    # Resolved lookup key for audit, e.g. "bug_fix:backend:major", "perf:size:m".
    rule_key: Mapped[str | None] = mapped_column(String(128))
    rules_version: Mapped[str | None] = mapped_column(String(32))
    # Snapshot of the tags that produced this row, e.g.
    # ["type:bug-fix", "sev:major", "area:backend", "triaged"].
    label_state: Mapped[dict | None] = mapped_column(JSONB)
    # The issue_tag_history row (triaged/reverted/rca-done) that triggered
    # this event, when applicable (NULL for the initial award).
    source_tag_event_id: Mapped[int | None] = mapped_column(BigInteger)
    # Set ONLY on a 'reversal' row: the original 'award' row it cancels.
    reverses_event_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("points_events.id", ondelete="SET NULL")
    )
    # Set ONLY on a 'bonus' row: the original incident 'award' row.
    related_event_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("points_events.id", ondelete="SET NULL")
    )
    # Which period this belongs to: the ticket's completed_at for awards, or
    # the triggering tag's detected_at for reversals/bonuses.
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # When this ledger row was actually written (which nightly run produced it).
    awarded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UnscoredTicket(Base):
    __tablename__ = "points_unscored_tickets"
    __table_args__ = (Index("ix_points_unscored_assignee_id", "assignee_id"),)

    issue_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("issues.id", ondelete="CASCADE"), primary_key=True
    )
    # missing_type | missing_bug_fields | missing_size | awaiting_triage |
    # awaiting_close | needs_review
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    assignee_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("actors.id", ondelete="SET NULL")
    )
    first_detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
