"""Async Zoho Sprints REST client.

Mirrors app/linear/client.py's shape (typed DTOs each carrying `raw: dict`
for raw_events landing, cursor/page walking, retry-with-backoff) with three
structural deltas Zoho's API forces:

1. OAuth2 refresh-token auth instead of a static personal API key — access
   tokens expire ~1hr, so every request goes through `_ensure_token()`,
   which refreshes lazily and retries once on a 401.
2. Index/range pagination (`index=1&range=100`) instead of GraphQL cursors.
3. A ~30 calls/min rate limit, tighter than Linear's — every request goes
   through a small in-process token-bucket limiter (`_RateLimiter`) before
   the reactive retry-on-429 backoff even comes into play.

IMPORTANT — field names/response envelope are UNVERIFIED against a live
account (Zoho's docs 403 automated fetches; this is built from third-party/
search-derived summaries). Every `from_node` classmethod below is the single
place to fix if the real shape differs — do not scatter field access beyond
these DTOs. Confirm before the first production sync: whether list responses
come back as a plain array under an obvious key (assumed below) or Zoho's
older columnar "_prop + parallel arrays" format seen on some legacy
endpoints; whether pagination exposes an explicit `hasMore`/`moreRecords`
flag (assumed absent below — falls back to "short page = last page").
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict

from app.config import get_settings

logger = logging.getLogger("app.zoho")

PAGE_SIZE = 100
MAX_RETRIES = 6


def _parse_dt(value: Any) -> datetime | None:
    """Zoho timestamps are commonly epoch-millis or ISO strings; accept both."""
    if value in (None, "", 0):
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000 if value > 10**12 else value, tz=UTC)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _s(value: Any) -> str | None:
    return str(value) if value is not None else None


# --------------------------------------------------------------------------- #
# Rate limiter — proactive token bucket, ~28 calls/min (safety margin under
# Zoho's documented ~30/min). Complements, doesn't replace, reactive 429
# backoff below: a burst from a *different* process can still 429 us.
# --------------------------------------------------------------------------- #
class _RateLimiter:
    def __init__(self, max_calls: int, period_s: float = 60.0):
        self._max_calls = max_calls
        self._period = period_s
        self._calls: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                while self._calls and now - self._calls[0] >= self._period:
                    self._calls.popleft()
                if len(self._calls) < self._max_calls:
                    self._calls.append(now)
                    return
                wait = self._period - (now - self._calls[0])
                await asyncio.sleep(max(wait, 0.05))


# --------------------------------------------------------------------------- #
# DTOs — each carries the original node in `raw` for raw_events landing.
# --------------------------------------------------------------------------- #
class ZohoTeam(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    name: str | None = None
    raw: dict[str, Any]

    @classmethod
    def from_node(cls, n: dict) -> ZohoTeam:
        return cls(id=_s(n.get("teamId") or n.get("id")), name=n.get("teamName") or n.get("name"), raw=n)


class ZohoProject(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    team_id: str | None = None
    key: str | None = None
    name: str | None = None
    archived_at: datetime | None = None
    raw: dict[str, Any]

    @classmethod
    def from_node(cls, n: dict, *, team_id: str | None = None) -> ZohoProject:
        return cls(
            id=_s(n.get("projectId") or n.get("id")),
            team_id=team_id or _s(n.get("teamId")),
            key=n.get("projectKey"),
            name=n.get("projectName") or n.get("name"),
            archived_at=_parse_dt(n.get("archivedTime")),
            raw=n,
        )


class ZohoUser(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    name: str | None = None
    email: str | None = None
    avatar_url: str | None = None
    active: bool = True
    raw: dict[str, Any]

    @classmethod
    def from_node(cls, n: dict) -> ZohoUser:
        return cls(
            id=_s(n.get("zuid") or n.get("userId") or n.get("id")),
            name=n.get("name") or n.get("userName"),
            email=n.get("email") or n.get("emailId"),
            avatar_url=n.get("photoURL") or n.get("avatarUrl"),
            active=bool(n.get("isActive", n.get("active", True))),
            raw=n,
        )


class ZohoSprint(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    project_id: str | None = None
    number: int | None = None
    name: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    completed_at: datetime | None = None
    raw: dict[str, Any]

    @classmethod
    def from_node(cls, n: dict, *, project_id: str | None = None) -> ZohoSprint:
        return cls(
            id=_s(n.get("sprintId") or n.get("id")),
            project_id=project_id or _s(n.get("projectId")),
            number=n.get("sprintNo"),
            name=n.get("sprintName") or n.get("name"),
            starts_at=_parse_dt(n.get("startDate")),
            ends_at=_parse_dt(n.get("endDate")),
            completed_at=_parse_dt(n.get("actualEndDate") or n.get("completedDate")),
            raw=n,
        )


class ZohoEpic(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    project_id: str | None = None
    name: str | None = None
    raw: dict[str, Any]

    @classmethod
    def from_node(cls, n: dict, *, project_id: str | None = None) -> ZohoEpic:
        return cls(
            id=_s(n.get("epicId") or n.get("id")),
            project_id=project_id or _s(n.get("projectId")),
            name=n.get("epicName") or n.get("name"),
            raw=n,
        )


class ZohoTag(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    team_id: str | None = None
    name: str
    color_code: str | None = None
    created_by: str | None = None
    raw: dict[str, Any]

    @classmethod
    def from_node(cls, n: dict, *, team_id: str | None = None) -> ZohoTag:
        return cls(
            id=_s(n.get("tagId") or n.get("id")),
            team_id=team_id or _s(n.get("teamId")),
            name=n.get("tagName") or n.get("name") or "",
            color_code=n.get("colorCode"),
            created_by=_s(n.get("createdBy")),
            raw=n,
        )


class ZohoItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    identifier: str | None = None
    title: str | None = None
    project_id: str | None = None
    sprint_id: str | None = None
    epic_id: str | None = None
    owner_id: str | None = None  # assignee
    created_by: str | None = None  # reporter
    completed_by: str | None = None
    status_id: str | None = None
    status_name: str | None = None
    priority_label: str | None = None
    points: float | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    canceled_at: datetime | None = None
    updated_at: datetime | None = None
    tag_ids: list[str] = []
    raw: dict[str, Any]

    @classmethod
    def from_node(cls, n: dict, *, project_id: str | None = None) -> ZohoItem:
        # Zoho's own "add-via" / status-group fields sometimes flag cancellation
        # (e.g. a dropped/cancelled status group) distinctly from completion;
        # absent a confirmed field, cancellation is left null here and resolved
        # by the status_defs mapping (see app/zoho/mapping.py) at normalize time.
        tags = n.get("tags") or n.get("tagDetails") or []
        tag_ids = [
            _s(t.get("tagId") or t.get("id")) for t in tags if isinstance(t, dict) and t.get("tagId") or t.get("id")
        ]
        return cls(
            id=_s(n.get("itemId") or n.get("id")),
            identifier=n.get("sequence") and f"#{n['sequence']}",
            title=n.get("itemName") or n.get("title"),
            project_id=project_id or _s(n.get("projectId")),
            sprint_id=_s(n.get("sprintId")),
            epic_id=_s(n.get("epicId")),
            owner_id=_s(n.get("ownerId")),
            created_by=_s(n.get("createdBy")),
            completed_by=_s(n.get("completedBy")),
            status_id=_s(n.get("statusId")),
            status_name=n.get("statusName"),
            priority_label=n.get("priorityName") or n.get("projPriorityId"),
            points=n.get("points"),
            created_at=_parse_dt(n.get("createdTime")),
            started_at=_parse_dt(n.get("startDate") or n.get("startAfter")),
            completed_at=_parse_dt(n.get("completedDate")),
            canceled_at=None,
            updated_at=_parse_dt(n.get("updatedTime") or n.get("lastModifiedTime")),
            tag_ids=[t for t in tag_ids if t],
            raw=n,
        )


class ZohoComment(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    item_id: str | None = None
    user_id: str | None = None
    body: str | None = None
    created_at: datetime | None = None
    raw: dict[str, Any]

    @classmethod
    def from_node(cls, n: dict, *, item_id: str | None = None) -> ZohoComment:
        return cls(
            id=_s(n.get("commentId") or n.get("id")),
            item_id=item_id or _s(n.get("itemId")),
            user_id=_s(n.get("commentedBy") or n.get("userId")),
            body=n.get("content") or n.get("comment"),
            created_at=_parse_dt(n.get("commentedTime") or n.get("createdTime")),
            raw=n,
        )


class ZohoSprintsClient:
    """Thin async REST client. Use as an async context manager."""

    def __init__(
        self,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        refresh_token: str | None = None,
        accounts_url: str | None = None,
        api_url: str | None = None,
        team_id: str | None = None,
        rate_limit_per_min: int | None = None,
        timeout: float = 30.0,
        http_transport: httpx.BaseTransport | None = None,
        auth_transport: httpx.BaseTransport | None = None,
    ):
        settings = get_settings()
        self._client_id = client_id or settings.zoho_client_id
        self._client_secret = client_secret or settings.zoho_client_secret
        self._refresh_token = refresh_token or settings.zoho_refresh_token
        self._accounts_url = (accounts_url or settings.zoho_accounts_url).rstrip("/")
        self._api_url = (api_url or settings.zoho_api_url).rstrip("/")
        self.team_id = team_id or settings.zoho_team_id
        if not (self._client_id and self._client_secret and self._refresh_token and self.team_id):
            raise RuntimeError(
                "Zoho Sprints is not configured (need client id/secret, refresh "
                "token, and team id)."
            )
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0
        self._limiter = _RateLimiter(rate_limit_per_min or settings.zoho_rate_limit_per_min)
        # `*_transport` are a test-only injection seam (httpx.MockTransport) —
        # None in production, which makes httpx use a real network transport.
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=10.0), transport=http_transport
        )
        self._auth_http = httpx.AsyncClient(
            base_url=self._accounts_url,
            timeout=httpx.Timeout(timeout, connect=10.0),
            transport=auth_transport,
        )

    async def __aenter__(self) -> ZohoSprintsClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()
        await self._auth_http.aclose()

    # --- OAuth --------------------------------------------------------- #
    async def _refresh_access_token(self) -> None:
        resp = await self._auth_http.post(
            "/oauth/v2/token",
            params={
                "refresh_token": self._refresh_token,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": "refresh_token",
            },
        )
        resp.raise_for_status()
        body = resp.json()
        if "access_token" not in body:
            raise RuntimeError(f"Zoho OAuth refresh failed: {body}")
        self._access_token = body["access_token"]
        # expires_in is seconds; refresh a bit early to avoid racing expiry.
        self._token_expires_at = time.monotonic() + float(body.get("expires_in", 3600)) - 60

    async def _ensure_token(self) -> str:
        if self._access_token is None or time.monotonic() >= self._token_expires_at:
            await self._refresh_access_token()
        assert self._access_token is not None
        return self._access_token

    # --- HTTP with retry/backoff + rate limiting ------------------------ #
    async def _request(self, method: str, path: str, *, params: dict | None = None) -> dict:
        attempt = 0
        forced_refresh = False
        while True:
            attempt += 1
            await self._limiter.acquire()
            token = await self._ensure_token()
            try:
                resp = await self._http.request(
                    method,
                    f"{self._api_url}{path}",
                    params=params,
                    headers={"Authorization": f"Zoho-oauthtoken {token}"},
                )
            except httpx.TransportError as exc:
                if attempt >= MAX_RETRIES:
                    raise
                delay = min(2**attempt, 30)
                logger.warning("Transport error (%s); retry %d in %ss", exc, attempt, delay)
                await asyncio.sleep(delay)
                continue

            if resp.status_code == 401 and not forced_refresh:
                # Access token likely expired early / was revoked — force one
                # refresh and retry, but only once, so a persistently invalid
                # refresh token still fails fast instead of looping forever.
                forced_refresh = True
                self._access_token = None
                continue

            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt >= MAX_RETRIES:
                    resp.raise_for_status()
                retry_after = resp.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else min(2**attempt, 30)
                logger.warning("HTTP %s from Zoho; retry %d in %ss", resp.status_code, attempt, delay)
                await asyncio.sleep(delay)
                continue

            resp.raise_for_status()
            return resp.json() if resp.content else {}

    async def _paginate(
        self, path: str, *, params: dict | None = None, items_key: str | None = None,
        page_size: int = PAGE_SIZE,
    ) -> list[dict]:
        """Walk an index/range-paginated list endpoint.

        No confirmed `hasMore` flag exists in the docs available to us — a
        page shorter than `page_size` is treated as the last page. If Zoho
        does expose an explicit flag, prefer it once confirmed (cheaper: no
        risk of stopping one page early on an exact-page-size-boundary list).
        """
        nodes: list[dict] = []
        index = 1
        while True:
            data = await self._request(
                "GET", path, params={**(params or {}), "index": index, "range": page_size, "action": "data"}
            )
            page = _extract_list(data, items_key)
            nodes.extend(page)
            if len(page) < page_size:
                break
            index += page_size
        return nodes

    # --- typed entity methods -------------------------------------------- #
    async def fetch_teams(self) -> list[ZohoTeam]:
        data = await self._request("GET", "/zsapi/teams/", params={"action": "data"})
        return [ZohoTeam.from_node(n) for n in _extract_list(data, "teams")]

    async def fetch_projects(self, team_id: str | None = None) -> list[ZohoProject]:
        tid = team_id or self.team_id
        nodes = await self._paginate(f"/zsapi/team/{tid}/projects/", items_key="projects")
        return [ZohoProject.from_node(n, team_id=tid) for n in nodes]

    async def fetch_project_users(self, project_id: str, team_id: str | None = None) -> list[ZohoUser]:
        tid = team_id or self.team_id
        nodes = await self._paginate(
            f"/zsapi/team/{tid}/projects/{project_id}/projectusers/", items_key="projectusers"
        )
        return [ZohoUser.from_node(n) for n in nodes]

    async def fetch_sprints(self, project_id: str, team_id: str | None = None) -> list[ZohoSprint]:
        tid = team_id or self.team_id
        nodes = await self._paginate(
            f"/zsapi/team/{tid}/projects/{project_id}/sprints/", items_key="sprints"
        )
        return [ZohoSprint.from_node(n, project_id=project_id) for n in nodes]

    async def fetch_epics(self, project_id: str, team_id: str | None = None) -> list[ZohoEpic]:
        tid = team_id or self.team_id
        nodes = await self._paginate(
            f"/zsapi/team/{tid}/projects/{project_id}/epic/", items_key="epic"
        )
        return [ZohoEpic.from_node(n, project_id=project_id) for n in nodes]

    async def fetch_tags(self, team_id: str | None = None) -> list[ZohoTag]:
        tid = team_id or self.team_id
        nodes = await self._paginate(f"/zsapi/team/{tid}/tags/", items_key="tags")
        return [ZohoTag.from_node(n, team_id=tid) for n in nodes]

    async def fetch_items(
        self, project_id: str, team_id: str | None = None, since: datetime | None = None
    ) -> list[ZohoItem]:
        """All items in a project. `since` is applied client-side by the
        caller (sync_zoho.py) via `updated_at` — no confirmed server-side
        "modified since" filter exists for this endpoint."""
        tid = team_id or self.team_id
        nodes = await self._paginate(
            f"/zsapi/team/{tid}/projects/{project_id}/sprints/0/items/", items_key="items"
        )
        return [ZohoItem.from_node(n, project_id=project_id) for n in nodes]

    async def fetch_item_comments(
        self, project_id: str, item_id: str, team_id: str | None = None
    ) -> list[ZohoComment]:
        """Comments for ONE item — no bulk endpoint. Callers should budget
        this per-item cost against the rate limit (see app/jobs/sync_zoho.py)."""
        tid = team_id or self.team_id
        nodes = await self._paginate(
            f"/zsapi/team/{tid}/projects/{project_id}/items/{item_id}/comments/",
            items_key="comments",
        )
        return [ZohoComment.from_node(n, item_id=item_id) for n in nodes]


def _extract_list(data: dict, items_key: str | None) -> list[dict]:
    """Unwrap a list response. Tries the given key, then a couple of common
    Zoho envelope shapes, falling back to "the first list value found"."""
    if items_key and isinstance(data.get(items_key), list):
        return data[items_key]
    for v in data.values():
        if isinstance(v, list):
            return v
    return []
