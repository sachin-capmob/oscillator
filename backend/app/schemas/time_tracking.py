"""Pydantic v2 schemas for the time-tracking API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ActorOut(BaseModel):
    """Minimal actor info for the people dropdown."""
    actor_id: int
    name: str | None = None
    email: str | None = None
    avatar_url: str | None = None


class TimeEntryStart(BaseModel):
    actor_id: int
    note: str | None = None


class TimeEntryStop(BaseModel):
    note: str | None = None


class TimeEntryOut(BaseModel):
    id: int
    actor_id: int
    actor_name: str | None = None
    actor_email: str | None = None
    started_at: datetime
    stopped_at: datetime | None = None
    duration_secs: int | None = None   # computed on read; None while running
    note: str | None = None


class ActiveTimerResp(BaseModel):
    entry: TimeEntryOut | None = None


class TimeLogResp(BaseModel):
    entries: list[TimeEntryOut]
    total: int


class TimeSummaryItem(BaseModel):
    actor_id: int
    actor_name: str | None = None
    actor_email: str | None = None
    total_secs: int
    session_count: int


class TimeSummaryResp(BaseModel):
    items: list[TimeSummaryItem]
