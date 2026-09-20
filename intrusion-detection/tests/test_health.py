from fastapi.testclient import TestClient
from backend.app.main import app


def test_health_and_api_schema():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert "/api/datasets" in client.get("/openapi.json").json()["paths"]


def test_baseline_not_trained_state(tmp_path, monkeypatch):
    from backend.app.config import settings
    monkeypatch.setattr(settings, "artifacts", tmp_path)
    with TestClient(app) as client:
        assert client.get("/api/baseline").json() == {"ready": False, "summary": None, "preview": []}
