"""Pydantic v2 response models for the insights API."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel


class Range(StrEnum):
    day = "day"
    week = "week"
    month = "month"


class Metric(BaseModel):
    """A KPI value with its previous-period comparison."""

    current: float | None = None
    previous: float | None = None
    delta_pct: float | None = None  # None when previous is 0/unknown


class OverviewResponse(BaseModel):
    range: Range
    period_start: datetime
    period_end: datetime
    throughput: Metric
    avg_cycle_hours: Metric
    comments: Metric
    wip: int          # point-in-time snapshot
    open_issues: int  # point-in-time snapshot


class TimeseriesPoint(BaseModel):
    period: date
    value: float | None = None


class DualPoint(BaseModel):
    """One time-bucket with both completed and created counts."""

    period: date
    completed: int = 0
    created: int = 0


class ThroughputResponse(BaseModel):
    range: Range
    unit: str
    series: list[DualPoint]  # each point has completed + created


class CycleTimePoint(BaseModel):
    period: date
    avg_hours: float | None = None
    median_hours: float | None = None


class CycleTimeResponse(BaseModel):
    range: Range
    unit: str
    series: list[CycleTimePoint]


class WipResponse(BaseModel):
    range: Range
    unit: str
    current: int
    series: list[TimeseriesPoint]


class ActorStat(BaseModel):
    actor_id: int
    name: str | None = None
    email: str | None = None
    avatar_url: str | None = None
    throughput: int
    avg_cycle_hours: float | None = None
    comments: int
    created: int = 0          # issues created (by creator_id) in the selected window
    sparkline: list[int]  # daily throughput, last 14 days


class ByActorResponse(BaseModel):
    range: Range
    period_start: datetime
    period_end: datetime
    actors: list[ActorStat]


class ActorThroughputPoint(BaseModel):
    """One time-bucket for a single actor — completed and created counts."""

    period: date
    completed: int = 0
    created: int = 0


class ActorThroughputStat(BaseModel):
    actor_id: int
    name: str | None = None
    email: str | None = None
    series: list[ActorThroughputPoint]


class ThroughputByActorResponse(BaseModel):
    range: Range
    unit: str
    actors: list[ActorThroughputStat]


class TeamStat(BaseModel):
    team_id: int
    name: str | None = None
    key: str | None = None
    throughput: int
    avg_cycle_hours: float | None = None
    median_cycle_hours: float | None = None
    wip: int
    comments: int
    scope_added: int


class ByTeamResponse(BaseModel):
    range: Range
    period_start: date
    teams: list[TeamStat]
