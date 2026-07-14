"""Pydantic v2 schemas for the custom-issues API."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class CustomIssueStatus(str, Enum):
    unstarted = "unstarted"
    started = "started"
    completed = "completed"
    canceled = "canceled"


class ActorOut(BaseModel):
    """Minimal actor info for the assignee dropdown."""
    actor_id: int
    name: str | None = None
    email: str | None = None
    avatar_url: str | None = None


class CustomIssueCreate(BaseModel):
    title: str
    assignee_id: int | None = None
    status: CustomIssueStatus = CustomIssueStatus.unstarted


class CustomIssueUpdate(BaseModel):
    title: str | None = None
    assignee_id: int | None = None
    status: CustomIssueStatus | None = None


class CustomIssueOut(BaseModel):
    id: int
    identifier: str | None = None
    title: str | None = None
    assignee_id: int | None = None
    assignee_name: str | None = None
    assignee_email: str | None = None
    status: str
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    canceled_at: datetime | None = None


class CustomIssueListResp(BaseModel):
    issues: list[CustomIssueOut]
    total: int
