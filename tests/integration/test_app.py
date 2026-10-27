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


def test_home_loads_ui_assets():
    with TestClient(app) as client:
        home = client.get("/").text
        for path in ("/static/app.js", "/static/app.css"):
            assert path in home
            asset = client.get(path)
            assert asset.status_code == 200
            assert asset.text.strip()
