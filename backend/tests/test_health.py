"""Smoke tests proving the skeleton boots and serves health endpoints."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_ready_reports_config_flags():
    resp = client.get("/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert "database_configured" in body
    assert "linear_configured" in body
