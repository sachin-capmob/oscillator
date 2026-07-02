"""Narrative digest generation.

Gathers the current-period overview deltas + the freshly detected anomalies and
turns them into a short human-readable summary. Prefers Groq (an OpenAI-compatible
chat-completions endpoint) and falls back to a deterministic templated summary
when Groq is unconfigured or the call fails — so the feature always produces a
digest.

One digest is generated per range for the "current" anchor (real now), then
UPSERTed on (range, anchor). The read API serves these cached rows.
"""

from __future__ import annotations

import logging
from datetime import date

import httpx
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Digest

logger = logging.getLogger("app.digest")

# Ranges we precompute a digest for on each sync. "all" is omitted — it has no
# prior-period comparison and rarely changes meaningfully sync-to-sync.
DIGEST_RANGES = ("day", "week", "month")

SYSTEM_PROMPT = (
    "You are an engineering-analytics assistant for a team using Linear. "
    "Given metrics and flagged anomalies for a time period, write a concise "
    "digest of what changed and why it matters. Rules: 3-5 sentences, plain "
    "prose (no markdown, no bullet lists, no headings), lead with the single "
    "most important change, name specific teams/numbers when given, and never "
    "invent data not present in the input. If nothing notable happened, say so "
    "briefly."
)

_SEVERITY_RANK = {"critical": 0, "warn": 1, "info": 2}


async def _gather_facts(session: AsyncSession, rng: str, anchor: date) -> dict:
    """Pull overview deltas + current anomalies into a compact facts dict."""
    # Local import avoids a module-load cycle (insights imports schemas, not us).
    from app.api.insights import _anomaly_bucket, _period_bounds, _ref
    from app.schemas.insights import Range

    r = Range(rng)
    ref = _ref(anchor)
    cs, ce, ps, pe = _period_bounds(r, ref)
    ov = (
        await session.execute(
            text(
                """
                SELECT
                  count(*) FILTER (WHERE completed_at >= :cs AND completed_at < :ce)::int AS thr_cur,
                  count(*) FILTER (WHERE completed_at >= :ps AND completed_at < :pe)::int AS thr_prev,
                  count(*) FILTER (WHERE created_at >= :cs AND created_at < :ce)::int AS cre_cur,
                  count(*) FILTER (WHERE created_at >= :ps AND created_at < :pe)::int AS cre_prev,
                  count(*) FILTER (
                    WHERE started_at < :ce
                      AND (completed_at IS NULL OR completed_at >= :ce)
                      AND (canceled_at IS NULL OR canceled_at >= :ce)
                  )::int AS wip
                FROM issues
                """
            ),
            {"cs": cs, "ce": ce, "ps": ps, "pe": pe},
        )
    ).mappings().one()

    bucket = _anomaly_bucket(r, ref)
    anomalies = (
        await session.execute(
            text(
                """
                SELECT scope, entity_name, metric, direction, severity,
                       observed, baseline, z_score
                FROM anomalies
                WHERE period = :bucket
                ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'warn' THEN 1 ELSE 2 END,
                         abs(z_score) DESC
                LIMIT 12
                """
            ),
            {"bucket": bucket},
        )
    ).mappings().all()

    return {
        "range": rng,
        "period_start": cs.date().isoformat(),
        "throughput": {"current": ov["thr_cur"], "previous": ov["thr_prev"]},
        "created": {"current": ov["cre_cur"], "previous": ov["cre_prev"]},
        "wip": ov["wip"],
        "anomalies": [dict(a) for a in anomalies],
    }


def _pct(cur: float, prev: float) -> str:
    """Magnitude of the period-over-period change; direction is stated separately."""
    if prev == 0:
        return "n/a" if cur == 0 else "new"
    return f"{abs(round((cur - prev) / prev * 100))}%"


def _template_summary(facts: dict) -> str:
    """Deterministic fallback narrative built from the facts dict."""
    rng = facts["range"]
    thr = facts["throughput"]
    cre = facts["created"]
    parts: list[str] = []

    dp = _pct(thr["current"], thr["previous"])
    verb = "up" if thr["current"] >= thr["previous"] else "down"
    parts.append(
        f"This {rng}, throughput was {thr['current']} completed "
        f"({verb} {dp} vs the previous {rng}), against {cre['current']} created."
    )
    net = cre["current"] - thr["current"]
    if net > 0:
        parts.append(f"The backlog grew by {net} (more created than completed).")
    elif net < 0:
        parts.append(f"The backlog shrank by {abs(net)} (more completed than created).")

    anomalies = facts["anomalies"]
    if anomalies:
        top = anomalies[:3]
        frags = []
        for a in top:
            who = a["entity_name"] or a["scope"]
            frags.append(
                f"{who} {a['metric'].replace('_', ' ')} {a['direction']} "
                f"({a['observed']:g} vs {a['baseline']:g} baseline)"
            )
        parts.append("Notable: " + "; ".join(frags) + ".")
        if len(anomalies) > 3:
            parts.append(f"{len(anomalies) - 3} further anomalies were flagged.")
    else:
        parts.append("No metric anomalies were flagged against recent baselines.")

    return " ".join(parts)


async def _groq_summary(facts: dict) -> str | None:
    """Call Groq's chat-completions endpoint. Returns None on any failure."""
    settings = get_settings()
    if not settings.groq_configured:
        return None
    import json

    user_msg = (
        "Write the digest for this data. Only use these facts:\n"
        + json.dumps(facts, default=str)
    )
    payload = {
        "model": settings.groq_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.3,
        "max_tokens": 320,
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
            resp = await client.post(
                settings.groq_api_url,
                headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        text_out = data["choices"][0]["message"]["content"].strip()
        return text_out or None
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        logger.warning("Groq digest failed (%s); using template fallback", exc)
        return None


async def generate_digests(session: AsyncSession, *, anchor: date) -> int:
    """Generate + UPSERT a digest per range for `anchor`. Returns rows written."""
    settings = get_settings()
    written = 0
    for rng in DIGEST_RANGES:
        facts = await _gather_facts(session, rng, anchor)
        summary = await _groq_summary(facts)
        source = "groq" if summary else "template"
        model = settings.groq_model if summary else None
        if not summary:
            summary = _template_summary(facts)

        stmt = pg_insert(Digest).values(
            range=rng,
            anchor=anchor,
            summary=summary,
            source=source,
            model=model,
            anomaly_count=len(facts["anomalies"]),
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_digest_key",
            set_={
                "summary": stmt.excluded.summary,
                "source": stmt.excluded.source,
                "model": stmt.excluded.model,
                "anomaly_count": stmt.excluded.anomaly_count,
                "generated_at": text("now()"),
            },
        )
        await session.execute(stmt)
        written += 1
    logger.info("Generated %d digests (anchor=%s)", written, anchor)
    return written
