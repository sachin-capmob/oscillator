"""The Engineering Points lookup tables — transcribed from the team's scoring
doc. Hardcoded, not DB-editable: every points_events row snapshots its
resolved `points` value + `rule_key` + `rules_version` at scoring time, so
ledger history stays correct regardless of later edits here. Changing a
value in this file is a normal, reviewed code change; it only affects
tickets scored AFTER the change ships, per "raise it at retro" in the doc.

Bump RULES_VERSION whenever any table below changes, so every ledger row
records exactly which rules produced it.
"""

from __future__ import annotations

RULES_VERSION = "2026-07-27-v1"

# --- Bug points: [area][severity] -> (find_points, fix_points) -------------
BUG_POINTS: dict[str, dict[str, tuple[int, int]]] = {
    "infra": {"critical": (5, 10), "major": (3, 6), "minor": (1, 2)},
    "backend": {"critical": (4, 8), "major": (2, 4), "minor": (1, 1)},
    "frontend": {"critical": (3, 6), "major": (2, 3), "minor": (1, 1)},
    "design": {"critical": (2, 3), "major": (1, 2), "minor": (1, 1)},
}

# --- Sized non-bug work: [category][size] -> points -------------------------
SIZED_POINTS: dict[str, dict[str, int]] = {
    "feature_be": {"s": 3, "m": 7, "l": 12},
    "feature_fe": {"s": 2, "m": 5, "l": 10},
    "infra": {"s": 3, "m": 7, "l": 12},
    "design": {"s": 2, "m": 4, "l": 8},
    "chore": {"s": 1, "m": 3, "l": 6},
    # Requires a before/after number in the PR — not label-derivable (see
    # app.jobs.score_points), so this table is only reached once that's
    # confirmed some other way; until then these tickets sit unscored.
    "perf": {"s": 2, "m": 5, "l": 10},
}

# --- Flat-rate categories: same value regardless of size --------------------
FLAT_POINTS: dict[str, int] = {
    "review": 1,  # trivial PRs (typo, dep bump) don't count — not label-derivable, see open questions
    "spike": 2,  # output is a decision doc
    "ux": 3,  # per session, requires writeup
    "analytics": 2,  # per event set wired up
    "copy_small": 1,  # error messages, microcopy
    "copy_large": 3,  # landing page, onboarding
    "a11y": 2,  # per screen or component
    "docs_small": 1,  # README section, inline docs
    "docs_large": 3,  # runbook, architecture doc, onboarding guide
    "ops_save": 5,  # caught before it broke
    "incident": 8,  # mitigated a live incident
    "incident_rca_bonus": 4,  # RCA writeup, added on top of the incident award
}

# --- Security fix: baseline 8, up to 15 for critical -------------------------
# The doc gives "8 baseline, up to 15 for critical" but worked example #9
# implies a finer scale exists ("10 for a mid-range security fix"). This
# proposed 3-point scale needs team confirmation (see open question #1 in
# the plan) — every type:security ticket is held in points_unscored_tickets
# with reason='needs_review' until a sec-severity label exists to select a
# tier, so nothing ships a guessed point value silently.
SECURITY_POINTS: dict[str, int] = {"baseline": 8, "major": 10, "critical": 15}

# --- type:* tag -> scoring category -----------------------------------------
# "bug-find"/"bug-fix" branch through BUG_POINTS (need sev:*/area:*);
# the SIZED_POINTS keys branch through size:*; everything else is flat-rate.
TYPE_TAG_TO_CATEGORY: dict[str, str] = {
    "type:bug-find": "bug_find",
    "type:bug-fix": "bug_fix",
    "type:feat-be": "feature_be",
    "type:feat-fe": "feature_fe",
    "type:infra": "infra",
    "type:design": "design",
    "type:chore": "chore",
    "type:perf": "perf",
    "type:review": "review",
    "type:spike": "spike",
    "type:ops-save": "ops_save",
    "type:incident": "incident",
    "type:security": "security",
    "type:ux": "ux",
    "type:analytics": "analytics",
    "type:copy": "copy",  # small/large resolved separately via size-ish tags, see score_points
    "type:a11y": "a11y",
    "type:docs": "docs",  # small/large resolved separately via size-ish tags, see score_points
}

BUG_CATEGORIES = {"bug_find", "bug_fix"}
SIZED_CATEGORIES = set(SIZED_POINTS.keys())

SEVERITY_LABELS = {"sev:critical": "critical", "sev:major": "major", "sev:minor": "minor"}
AREA_LABELS = {
    "area:infra": "infra",
    "area:backend": "backend",
    "area:frontend": "frontend",
    "area:design": "design",
}
SIZE_LABELS = {"size:s": "s", "size:m": "m", "size:l": "l"}

TRIAGED_TAG = "triaged"
REVERTED_TAG = "reverted"
RCA_DONE_TAG = "rca-done"
OWN_CODE_TAG = "own-code"  # proposed self-report tag, see open question #2
TRIVIAL_TAG = "trivial"  # proposed opt-out tag, see open question #3
