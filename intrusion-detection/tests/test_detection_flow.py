"""Actual HTTP -> SQLite -> worker -> model -> CSV integration, isolated per test."""
import io
import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.config import settings
from backend.app.database import Base, get_db
from backend.app.db_models import DetectionTask, Dataset, ModelVersion
from backend.app.main import app
from ml.train import fit_model, save_model_pack_from_fit
from worker import worker


@pytest.fixture
def flow(tmp_path, monkeypatch):
    import backend.app.main as main_module
    for key in ("data_raw", "data_processed", "artifacts", "configs"):
        directory = tmp_path / key
        directory.mkdir()
        monkeypatch.setattr(settings, key, directory)
    (settings.configs / "feature_schema.json").write_text(json.dumps({"numeric": ["dur"], "categorical": ["proto"]}))
    df = pd.DataFrame({"dur": [0., 1., 10., 11.], "proto": ["tcp", "udp", "tcp", "udp"]})
    pipeline = fit_model(df, pd.Series([0, 0, 1, 1]), "decision_tree", {"random_state": 42})
    save_model_pack_from_fit(pipeline, list(df.columns), {"0": "正常", "1": "攻击"}, .5,
                            settings.artifacts / "baseline", {"name": "random_forest"})
    df.to_csv(settings.data_processed / "demo_input.csv", index=False)
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(main_module, "engine", engine)
    monkeypatch.setattr(worker, "SessionLocal", sessions)
    def db_override():
        with sessions() as db:
            yield db
    app.dependency_overrides[get_db] = db_override
    try:
        with TestClient(app) as client:
            yield client, sessions
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def create_task(client):
    dataset = client.post("/api/datasets/demo").json()
    model = client.get("/api/models").json()[0]
    response = client.post("/api/detections", json={"dataset_id": dataset["id"], "model_id": model["id"]})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_upload_worker_filters_and_export(flow):
    client, sessions = flow
    upload = client.post("/api/datasets", files={"file": ("sample.csv", b"dur,proto\n0,tcp\n1,udp\n10,tcp\n11,udp\n", "text/csv")})
    assert upload.status_code == 201, upload.text
    dataset = upload.json()
    assert dataset["row_count"] == 4
    assert client.get(f"/api/datasets/{dataset['id']}/preview").json()["columns"] == ["dur", "proto"]
    model = client.get("/api/models").json()[0]
    assert len(client.get("/api/models").json()) == 1
    response = client.post("/api/detections", json={"dataset_id": dataset["id"], "model_id": model["id"]})
    task_id = response.json()["id"]
    assert client.get(f"/api/detections/{task_id}/results").status_code == 409
    assert worker.run_once()
    assert not worker.run_once()
    task = client.get(f"/api/detections/{task_id}").json()
    assert task["status"] == "succeeded", task
    assert task["processed_rows"] == 4
    filtered = client.get(f"/api/detections/{task_id}/results?label=1&page_size=1&page=2")
    assert filtered.status_code == 200, filtered.text
    assert filtered.json()["total"] == 2
    assert filtered.json()["items"][0]["source_row_id"] == 3
    stats = client.get(f"/api/detections/{task_id}/statistics?label=1").json()
    assert stats == {"total": 2, "attack": 2, "normal": 0, "attack_ratio": 1}
    exported = client.get(f"/api/detections/{task_id}/report?label=1")
    assert exported.status_code == 200
    frame = pd.read_csv(io.BytesIO(exported.content))
    assert len(frame) == stats["total"]
    assert frame.predicted_name.tolist() == ["攻击", "攻击"]
    assert exported.content.startswith(b"\xef\xbb\xbf")
    assert client.get(f"/api/detections/{task_id}/results?page=0").status_code == 422


@pytest.mark.parametrize("content", [b"", b"dur,proto\n", b"dur\n1\n", b"dur,dur,proto\n1,2,tcp\n", b"dur,proto\nno,tcp\n", b"dur,proto\ninf,tcp\n"])
def test_invalid_upload_not_registered(flow, content):
    client, sessions = flow
    response = client.post("/api/datasets", files={"file": ("bad.csv", content)})
    assert response.status_code == 422, response.text
    assert client.get("/api/datasets").json() == []
    assert not list((settings.data_raw / "uploads").glob("*.csv"))


def test_interruption_retry_and_changed_data_failure(flow):
    client, sessions = flow
    task_id = create_task(client)
    assert worker._claim_next_task() == task_id
    worker._mark_interrupted_on_startup()
    assert client.get(f"/api/detections/{task_id}").json()["status"] == "interrupted"
    response = client.post(f"/api/detections/{task_id}/retry")
    retry_id = response.json()["id"]
    assert retry_id != task_id
    with sessions() as db:
        dataset = db.get(Dataset, db.get(DetectionTask, retry_id).dataset_id)
        from pathlib import Path
        Path(dataset.path).write_text("dur,proto\n9,tcp\n")
    worker.run_once()
    result = client.get(f"/api/detections/{retry_id}").json()
    assert result["status"] == "failed"
    assert "发生变化" in result["error"]
    assert client.get(f"/api/detections/{retry_id}/report").status_code == 409


def test_registered_model_is_frozen(flow):
    client, sessions = flow
    task_id = create_task(client)
    source = settings.artifacts / "baseline/random_forest.pack_joblib"
    source.write_bytes(b"changed baseline")
    worker.run_once()
    assert client.get(f"/api/detections/{task_id}").json()["status"] == "succeeded"
