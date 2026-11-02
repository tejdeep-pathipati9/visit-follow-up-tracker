"""The React application and printable report assets are served by FastAPI."""

import re

from fastapi.testclient import TestClient
import pytest

from app.main import app
import app.main as main


@pytest.mark.skipif(not (main.UI_DIST / "index.html").is_file(), reason="Build ui/ first to verify compiled assets")
def test_app_starts_and_serves_built_ui_assets():
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json() == {"status": "ok"}
        home = client.get("/")
        assert home.status_code == 200
        assert "text/html" in home.headers["content-type"]
        assert "Visit Follow-Up Tracker" in home.text
        assert "Synthetic data only" in home.text
        assert home.headers["cache-control"] == "no-cache"
        assets = re.findall(r'(?:src|href)="(/assets/[^" ]+)"', home.text)
        assert assets
        for path in assets:
            response = client.get(path)
            assert response.status_code == 200
            assert response.content
        assert client.get("/static/report.css").status_code == 200


def test_missing_ui_build_explains_how_to_start_it(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "UI_DIST", tmp_path / "not-built")
    with TestClient(app) as client:
        home = client.get("/")
        assert home.status_code == 503
        assert "npm run build --prefix ui" in home.text
        assert client.get("/health").status_code == 200
