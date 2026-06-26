"""Shared API dependencies: bearer-token auth for the insights endpoints."""

from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, status

from app.config import get_settings


async def require_token(authorization: str = Header(default="")) -> None:
    """Validate `Authorization: Bearer <DASHBOARD_AUTH_TOKEN>` in constant time."""
    settings = get_settings()
    expected = settings.dashboard_auth_token
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DASHBOARD_AUTH_TOKEN is not configured on the server.",
        )
    prefix = "Bearer "
    provided = authorization[len(prefix):] if authorization.startswith(prefix) else ""
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
