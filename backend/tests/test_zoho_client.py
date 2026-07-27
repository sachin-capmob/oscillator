"""Unit tests for ZohoSprintsClient's OAuth refresh, retry/backoff, rate
limiting, and pagination — all pure-Python logic testable with
httpx.MockTransport, with no live Zoho account required. Field-shape
assumptions (see app/zoho/client.py's module docstring) are exercised with
representative fixture JSON, not verified against a real response.
"""

from __future__ import annotations

import time

import httpx
import pytest

from app.zoho.client import ZohoItem, ZohoSprintsClient, ZohoTag, ZohoTeam, _RateLimiter


def _client(handler, **kwargs) -> ZohoSprintsClient:
    return ZohoSprintsClient(
        client_id="cid",
        client_secret="csecret",
        refresh_token="rtoken",
        team_id="team-1",
        accounts_url="https://accounts.zoho.test",
        api_url="https://sprintsapi.zoho.test",
        http_transport=httpx.MockTransport(handler),
        auth_transport=httpx.MockTransport(_token_handler),
        **kwargs,
    )


def _token_handler(request: httpx.Request) -> httpx.Response:
    assert request.url.path == "/oauth/v2/token"
    return httpx.Response(200, json={"access_token": "tok-1", "expires_in": 3600})


@pytest.mark.asyncio
async def test_oauth_token_is_fetched_and_cached():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.headers["Authorization"])
        return httpx.Response(200, json={"teams": [{"teamId": "t1", "teamName": "Core"}]})

    async with _client(handler) as client:
        await client.fetch_teams()
        await client.fetch_teams()

    # Same cached token reused across both calls — no re-refresh.
    assert calls == ["Zoho-oauthtoken tok-1", "Zoho-oauthtoken tok-1"]


@pytest.mark.asyncio
async def test_teams_parse_into_dtos():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"teams": [{"teamId": "t1", "teamName": "Core"}, {"teamId": "t2", "teamName": "Growth"}]}
        )

    async with _client(handler) as client:
        teams = await client.fetch_teams()

    assert [t.id for t in teams] == ["t1", "t2"]
    assert all(isinstance(t, ZohoTeam) for t in teams)


@pytest.mark.asyncio
async def test_401_forces_one_refresh_then_succeeds():
    token_calls = {"n": 0}

    def token_handler(request: httpx.Request) -> httpx.Response:
        token_calls["n"] += 1
        return httpx.Response(200, json={"access_token": f"tok-{token_calls['n']}", "expires_in": 3600})

    attempts = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request.headers["Authorization"])
        if len(attempts) == 1:
            return httpx.Response(401, json={"error": "expired"})
        return httpx.Response(200, json={"teams": []})

    client = ZohoSprintsClient(
        client_id="cid", client_secret="csecret", refresh_token="rtoken", team_id="team-1",
        accounts_url="https://accounts.zoho.test", api_url="https://sprintsapi.zoho.test",
        http_transport=httpx.MockTransport(handler),
        auth_transport=httpx.MockTransport(token_handler),
    )
    async with client:
        teams = await client.fetch_teams()

    assert teams == []
    assert attempts == ["Zoho-oauthtoken tok-1", "Zoho-oauthtoken tok-2"]  # forced refresh happened once
    assert token_calls["n"] == 2


@pytest.mark.asyncio
async def test_429_retries_with_retry_after():
    attempts = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={})
        return httpx.Response(200, json={"teams": []})

    async with _client(handler) as client:
        teams = await client.fetch_teams()

    assert teams == []
    assert len(attempts) == 2


@pytest.mark.asyncio
async def test_pagination_walks_index_range_until_short_page():
    pages = [
        [{"itemId": f"i{i}"} for i in range(3)],  # full page (range=3) -> keep going
        [{"itemId": "i3"}],  # short page -> stop
    ]
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        idx = calls["n"]
        calls["n"] += 1
        return httpx.Response(200, json={"items": pages[idx]})

    async with _client(handler) as client:
        nodes = await client._paginate("/zsapi/team/team-1/x/", items_key="items", page_size=3)

    assert [n["itemId"] for n in nodes] == ["i0", "i1", "i2", "i3"]
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_item_and_tag_dto_field_mapping():
    node = {
        "itemId": "item-1",
        "itemName": "Fix the thing",
        "sequence": 42,
        "projectId": "proj-1",
        "sprintId": "sprint-1",
        "epicId": "epic-1",
        "ownerId": "user-2",
        "createdBy": "user-1",
        "completedBy": "user-2",
        "statusId": "status-done",
        "statusName": "Done",
        "points": 3.0,
        "createdTime": "2026-07-01T00:00:00Z",
        "completedDate": "2026-07-05T00:00:00Z",
        "updatedTime": "2026-07-05T00:00:00Z",
        "tags": [{"tagId": "tag-1"}, {"tagId": "tag-2"}],
    }
    item = ZohoItem.from_node(node, project_id="proj-1")
    assert item.id == "item-1"
    assert item.title == "Fix the thing"
    assert item.owner_id == "user-2"
    assert item.created_by == "user-1"
    assert item.completed_by == "user-2"
    assert item.status_name == "Done"
    assert item.points == 3.0
    assert set(item.tag_ids) == {"tag-1", "tag-2"}

    tag = ZohoTag.from_node({"tagId": "tag-1", "tagName": "type:bug-fix", "colorCode": "#fff"}, team_id="team-1")
    assert tag.name == "type:bug-fix"
    assert tag.team_id == "team-1"


@pytest.mark.asyncio
async def test_rate_limiter_blocks_beyond_budget():
    limiter = _RateLimiter(max_calls=2, period_s=0.2)
    start = time.monotonic()
    await limiter.acquire()
    await limiter.acquire()
    # Third call must wait for the window to roll over.
    await limiter.acquire()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.15
