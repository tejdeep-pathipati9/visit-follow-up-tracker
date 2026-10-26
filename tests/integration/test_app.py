"""Startup smoke checks only; the full business workflow is not covered yet."""

from fastapi.testclient import TestClient

from app.main import app


def test_app_starts_and_renders_home():
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json() == {"status": "ok"}

        home = client.get("/")
        assert home.status_code == 200
        assert "text/html" in home.headers["content-type"]
        assert "Visit Follow-Up Tracker" in home.text
        assert "Synthetic data only" in home.text
