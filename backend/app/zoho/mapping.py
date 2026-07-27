"""Zoho status -> our normalized state_type mapping.

Zoho Sprints statuses are project-configurable (unlike Linear's fixed
6-value state_type enum), so there is no universal id->state_type table.
Instead, `classify_status_name` seeds a best-effort guess from the status's
display name the first time a project's status is seen; that guess is
persisted in `status_defs` (keyed on (project_id, zoho_status_id)) so it is
looked up — not re-guessed — on every subsequent sync, and can be hand-
corrected directly in the table if a project's status naming is unusual.
"""

from __future__ import annotations

# triage | backlog | unstarted | started | completed | canceled
_COMPLETED_HINTS = ("done", "closed", "resolved", "shipped", "complete", "released")
_CANCELED_HINTS = ("cancel", "rejected", "invalid", "duplicate", "won't fix", "wont fix")
_STARTED_HINTS = ("progress", "wip", "active", "in review", "review", "testing", "qa")
_TRIAGE_HINTS = ("triage", "unconfirmed", "needs info", "incoming")
_BACKLOG_HINTS = ("backlog", "open", "new", "to do", "todo")


def classify_status_name(name: str | None) -> str:
    """Best-effort default for a never-before-seen Zoho status name."""
    n = (name or "").strip().lower()
    if not n:
        return "unstarted"
    for hints, state_type in (
        (_COMPLETED_HINTS, "completed"),
        (_CANCELED_HINTS, "canceled"),
        (_STARTED_HINTS, "started"),
        (_TRIAGE_HINTS, "triage"),
        (_BACKLOG_HINTS, "backlog"),
    ):
        if any(h in n for h in hints):
            return state_type
    return "unstarted"
