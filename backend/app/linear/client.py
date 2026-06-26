"""Async Linear GraphQL client.

Auth uses the personal API key as the raw ``Authorization`` header value (no
"Bearer" prefix) — that is how Linear authenticates personal API keys.

Handles cursor pagination (pageInfo.hasNextPage/endCursor) and 429 / 5xx with
exponential backoff that respects a ``Retry-After`` header when present.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict

from app.config import get_settings

logger = logging.getLogger("app.linear")

LINEAR_API_URL = "https://api.linear.app/graphql"
PAGE_SIZE = 100
MAX_RETRIES = 6
# Full backfill sentinel: updatedAt > epoch matches every record.
FULL_BACKFILL_SINCE = datetime(1970, 1, 1, tzinfo=UTC)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    # Python 3.11+ fromisoformat handles the trailing 'Z'.
    return datetime.fromisoformat(value)


def _nested_id(node: dict, key: str) -> str | None:
    obj = node.get(key)
    return obj.get("id") if isinstance(obj, dict) else None


# --------------------------------------------------------------------------- #
# DTOs — each carries the original GraphQL node in `raw` for raw_events landing.
# --------------------------------------------------------------------------- #
class LinearTeam(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    key: str | None = None
    name: str | None = None
    archived_at: datetime | None = None
    raw: dict[str, Any]

    @classmethod
    def from_node(cls, n: dict) -> LinearTeam:
        return cls(id=n["id"], key=n.get("key"), name=n.get("name"),
                   archived_at=_parse_dt(n.get("archivedAt")), raw=n)


class LinearUser(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    name: str | None = None
    email: str | None = None
    avatar_url: str | None = None
    active: bool = True
    raw: dict[str, Any]

    @classmethod
    def from_node(cls, n: dict) -> LinearUser:
        return cls(id=n["id"], name=n.get("name"), email=n.get("email"),
                   avatar_url=n.get("avatarUrl"), active=bool(n.get("active", True)), raw=n)


class LinearIssue(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    identifier: str | None = None
    title: str | None = None
    team_id: str | None = None
    assignee_id: str | None = None
    creator_id: str | None = None
    cycle_id: str | None = None
    project_id: str | None = None
    state: str | None = None
    state_type: str | None = None
    priority: int | None = None
    estimate: float | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    canceled_at: datetime | None = None
    updated_at: datetime | None = None
    raw: dict[str, Any]

    @classmethod
    def from_node(cls, n: dict) -> LinearIssue:
        state = n.get("state") or {}
        return cls(
            id=n["id"], identifier=n.get("identifier"), title=n.get("title"),
            team_id=_nested_id(n, "team"), assignee_id=_nested_id(n, "assignee"),
            creator_id=_nested_id(n, "creator"), cycle_id=_nested_id(n, "cycle"),
            project_id=_nested_id(n, "project"),
            state=state.get("name"), state_type=state.get("type"),
            priority=n.get("priority"), estimate=n.get("estimate"),
            created_at=_parse_dt(n.get("createdAt")),
            started_at=_parse_dt(n.get("startedAt")),
            completed_at=_parse_dt(n.get("completedAt")),
            canceled_at=_parse_dt(n.get("canceledAt")),
            updated_at=_parse_dt(n.get("updatedAt")), raw=n,
        )


class LinearComment(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    issue_id: str | None = None
    user_id: str | None = None
    body: str | None = None
    created_at: datetime | None = None
    raw: dict[str, Any]

    @classmethod
    def from_node(cls, n: dict) -> LinearComment:
        return cls(id=n["id"], issue_id=_nested_id(n, "issue"), user_id=_nested_id(n, "user"),
                   body=n.get("body"), created_at=_parse_dt(n.get("createdAt")), raw=n)


class LinearCycle(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    team_id: str | None = None
    number: int | None = None
    name: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    completed_at: datetime | None = None
    raw: dict[str, Any]

    @classmethod
    def from_node(cls, n: dict) -> LinearCycle:
        return cls(id=n["id"], team_id=_nested_id(n, "team"), number=n.get("number"),
                   name=n.get("name"), starts_at=_parse_dt(n.get("startsAt")),
                   ends_at=_parse_dt(n.get("endsAt")),
                   completed_at=_parse_dt(n.get("completedAt")), raw=n)


# --------------------------------------------------------------------------- #
# GraphQL documents. `since` always present (epoch for full backfill).
# --------------------------------------------------------------------------- #
_TEAMS = """
query($first:Int!,$after:String){
  teams(first:$first, after:$after){
    nodes{ id key name archivedAt }
    pageInfo{ hasNextPage endCursor }
  }
}"""

_USERS = """
query($first:Int!,$after:String){
  users(first:$first, after:$after){
    nodes{ id name email avatarUrl active }
    pageInfo{ hasNextPage endCursor }
  }
}"""

_ISSUES = """
query($first:Int!,$after:String,$since:DateTimeOrDuration!){
  issues(first:$first, after:$after, filter:{ updatedAt:{ gt:$since } }){
    nodes{
      id identifier title priority estimate
      createdAt startedAt completedAt canceledAt updatedAt
      state{ name type } assignee{ id } creator{ id } team{ id } cycle{ id } project{ id }
    }
    pageInfo{ hasNextPage endCursor }
  }
}"""

_COMMENTS = """
query($first:Int!,$after:String,$since:DateTimeOrDuration!){
  comments(first:$first, after:$after, filter:{ updatedAt:{ gt:$since } }){
    nodes{ id body createdAt user{ id } issue{ id } }
    pageInfo{ hasNextPage endCursor }
  }
}"""

_CYCLES = """
query($first:Int!,$after:String,$since:DateTimeOrDuration!){
  cycles(first:$first, after:$after, filter:{ updatedAt:{ gt:$since } }){
    nodes{ id number name startsAt endsAt completedAt team{ id } }
    pageInfo{ hasNextPage endCursor }
  }
}"""


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


class LinearClient:
    """Thin async GraphQL client. Use as an async context manager."""

    def __init__(self, api_key: str | None = None, *, timeout: float = 30.0):
        self._api_key = api_key or get_settings().linear_api_key
        if not self._api_key:
            raise RuntimeError("LINEAR_API_KEY is not configured.")
        self._client = httpx.AsyncClient(
            base_url=LINEAR_API_URL,
            headers={"Authorization": self._api_key, "Content-Type": "application/json"},
            timeout=httpx.Timeout(timeout, connect=10.0),
        )

    async def __aenter__(self) -> LinearClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _execute(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        """POST a GraphQL document with retry/backoff on 429 + 5xx."""
        attempt = 0
        while True:
            attempt += 1
            try:
                resp = await self._client.post("", json={"query": query, "variables": variables})
            except httpx.TransportError as exc:
                if attempt >= MAX_RETRIES:
                    raise
                delay = min(2 ** attempt, 30)
                logger.warning("Transport error (%s); retry %d in %ss", exc, attempt, delay)
                await asyncio.sleep(delay)
                continue

            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt >= MAX_RETRIES:
                    resp.raise_for_status()
                retry_after = resp.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else min(2 ** attempt, 30)
                logger.warning(
                    "HTTP %s from Linear; retry %d in %ss", resp.status_code, attempt, delay
                )
                await asyncio.sleep(delay)
                continue

            resp.raise_for_status()
            body = resp.json()
            if body.get("errors"):
                raise RuntimeError(f"Linear GraphQL errors: {body['errors']}")
            return body["data"]

    async def _paginate(self, query: str, root: str, variables: dict[str, Any]) -> list[dict]:
        """Walk a connection by cursor, returning all raw nodes."""
        nodes: list[dict] = []
        after: str | None = None
        while True:
            data = await self._execute(query, {**variables, "first": PAGE_SIZE, "after": after})
            conn = data[root]
            nodes.extend(conn["nodes"])
            page = conn["pageInfo"]
            if not page.get("hasNextPage"):
                break
            after = page["endCursor"]
        return nodes

    # --- typed entity methods ---
    async def fetch_teams(self) -> list[LinearTeam]:
        nodes = await self._paginate(_TEAMS, "teams", {})
        return [LinearTeam.from_node(n) for n in nodes]

    async def fetch_users(self) -> list[LinearUser]:
        nodes = await self._paginate(_USERS, "users", {})
        return [LinearUser.from_node(n) for n in nodes]

    async def fetch_issues(self, since: datetime | None = None) -> list[LinearIssue]:
        s = _iso(since or FULL_BACKFILL_SINCE)
        nodes = await self._paginate(_ISSUES, "issues", {"since": s})
        return [LinearIssue.from_node(n) for n in nodes]

    async def fetch_comments(self, since: datetime | None = None) -> list[LinearComment]:
        s = _iso(since or FULL_BACKFILL_SINCE)
        nodes = await self._paginate(_COMMENTS, "comments", {"since": s})
        return [LinearComment.from_node(n) for n in nodes]

    async def fetch_cycles(self, since: datetime | None = None) -> list[LinearCycle]:
        s = _iso(since or FULL_BACKFILL_SINCE)
        nodes = await self._paginate(_CYCLES, "cycles", {"since": s})
        return [LinearCycle.from_node(n) for n in nodes]
