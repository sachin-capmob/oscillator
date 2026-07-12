"""Pydantic v2 response models for the insights API."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel


class Range(StrEnum):
    day = "day"
    week = "week"
    month = "month"
    all = "all"


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


class AnomalyItem(BaseModel):
    """A single flagged metric deviation."""

    scope: str            # workspace | team | actor
    entity_id: int | None = None
    entity_name: str | None = None
    metric: str           # throughput | cycle_time | wip | net_flow | created
    period: date
    direction: str        # up | down
    severity: str         # warn | critical
    observed: float
    baseline: float
    stddev: float | None = None
    z_score: float


class AnomaliesResponse(BaseModel):
    period: date
    count: int
    anomalies: list[AnomalyItem]


class DigestResponse(BaseModel):
    range: Range
    anchor: date
    summary: str
    source: str           # groq | template
    model: str | None = None
    anomaly_count: int
    generated_at: datetime | None = None
    # False when no digest has been generated yet (pre-first-sync). The UI can
    # then hide the banner rather than show a stale/empty message.
    available: bool = True


class ActorIssue(BaseModel):
    """A single issue closed by an actor in the selected window."""

    issue_id: int
    title: str | None = None
    identifier: str | None = None   # e.g. "ENG-123"
    team_name: str | None = None
    completed_at: datetime | None = None
    cycle_hours: float | None = None  # hours from started_at → completed_at


class ActorIssuesResponse(BaseModel):
    actor_id: int
    name: str | None = None
    email: str | None = None
    range: Range
    period_start: datetime
    period_end: datetime
    issues: list[ActorIssue]
