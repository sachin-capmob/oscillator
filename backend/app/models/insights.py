"""Derived-analytics tables written by the cron sync (not from Linear directly).

``Anomaly`` holds statistical flags computed over the materialized rollups;
``Digest`` caches the LLM (or templated) narrative per (range, anchor) so the
read API never calls the LLM inline. See app/services/anomaly.py and
app/services/digest.py for the producers.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Float,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Anomaly(Base):
    """One flagged metric deviation for an entity in a period.

    Upserted on the natural key (scope, entity_id, metric, period) so a
    re-detected period never duplicates.
    """

    __tablename__ = "anomalies"
    __table_args__ = (
        UniqueConstraint("scope", "entity_id", "metric", "period", name="uq_anomaly_key"),
        Index("ix_anomalies_period", "period"),
        Index("ix_anomalies_severity", "severity"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)  # workspace|team|actor
    entity_id: Mapped[int | None] = mapped_column(BigInteger)  # NULL for workspace scope
    entity_name: Mapped[str | None] = mapped_column(String(255))
    metric: Mapped[str] = mapped_column(String(32), nullable=False)
    period: Mapped[date] = mapped_column(Date, nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)  # up|down
    severity: Mapped[str] = mapped_column(String(16), nullable=False)  # info|warn|critical
    observed: Mapped[float] = mapped_column(Float, nullable=False)
    baseline: Mapped[float] = mapped_column(Float, nullable=False)
    stddev: Mapped[float | None] = mapped_column(Float)
    z_score: Mapped[float] = mapped_column(Float, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Digest(Base):
    """Cached narrative summary for one (range, anchor). Regenerated each sync."""

    __tablename__ = "digests"
    __table_args__ = (
        UniqueConstraint("range", "anchor", name="uq_digest_key"),
        Index("ix_digests_generated_at", "generated_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    range: Mapped[str] = mapped_column(String(8), nullable=False)
    anchor: Mapped[date] = mapped_column(Date, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # groq|template
    model: Mapped[str | None] = mapped_column(String(128))
    anomaly_count: Mapped[int] = mapped_column(Integer, server_default=text("0"), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
