"""实验API、训练Worker及检测模型通道的实际集成验证。"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine, text, inspect

from tests.test_detection_flow import flow  # 复用独立数据库与临时模型夹具
from backend.app.config import settings
from backend.app.database import initialize_database
from backend.app.db_models import Dataset, Experiment, ModelVersion
from worker import worker


def training_dataset(client, labelled=True):
    rng = np.random.default_rng(42)
    frame = pd.DataFrame({"dur": np.linspace(0, 20, 120), "proto": rng.choice(["tcp", "udp"], 120)})
    if labelled:
        frame["label"] = (frame.dur > 10).astype(int)
        frame["attack_cat"] = frame.label.map({0: "Normal", 1: "DoS"})
        frame["id"] = range(len(frame))
    response = client.post("/api/datasets", files={"file": ("train.csv", frame.to_csv(index=False).encode())})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def submit(client, dataset_id, algorithm="decision_tree", **extra):
    response = client.post("/api/experiments", json={"dataset_id": dataset_id, "algorithm": algorithm, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def test_three_algorithms_traceable_comparable_and_detectable(flow):
    client, sessions = flow
    dataset_id = training_dataset(client)
    identifiers = []
    for algorithm in ("logistic_regression", "decision_tree", "random_forest"):
        item = submit(client, dataset_id, algorithm)
        identifiers.append(item["id"])
        assert item["status"] == "queued"
        assert client.get("/health").status_code == 200
    for _ in identifiers:
        assert worker.run_once()
    rows = client.get("/api/experiments").json()
    assert len(rows) == 3
    assert len({r["comparison_key"] for r in rows}) == 1
    models = client.get("/api/models").json()
    for row in rows:
        assert row["status"] == "succeeded", row
        assert row["progress"] == 100 and row["train_rows"] + row["validation_rows"] == 120
        assert row["train_seconds"] > 0 and len(row["logs"]) >= 6
        assert set(row["metrics"]) >= {"accuracy", "recall", "f1", "fpr"}
        assert row["dataset_hash"] and row["created_at"] and row["started_at"] and row["finished_at"]
        assert row["algorithm_name"] in next(m["name"] for m in models if m["id"] == row["model_id"])
        with sessions() as db:
            model = db.get(ModelVersion, row["model_id"])
            meta = json.loads(Path(model.artifact_path).with_suffix(".pack_meta.json").read_text(encoding="utf-8"))
            assert meta["feature_list"] == ["dur", "proto"]
            assert meta["params"] == row["params"]
            assert meta["dataset_hash"] == row["dataset_hash"]
            split = json.loads((Path(model.artifact_path).parent / "split.json").read_text())
            assert not set(split["train_rows"]) & set(split["validation_rows"])
        detection = client.post("/api/detections", json={"dataset_id": dataset_id, "model_id": row["model_id"]}).json()
        assert worker.run_once()
        assert client.get(f"/api/detections/{detection['id']}").json()["status"] == "succeeded"


def test_crud_recovery_failure_and_comparison_protocol(flow):
    client, sessions = flow
    dataset_id = training_dataset(client)
    first = submit(client, dataset_id)
    second = submit(client, dataset_id, seed=7)
    assert first["comparison_key"] != second["comparison_key"]
    renamed = client.patch(f"/api/experiments/{first['id']}", json={"name": "重新命名"})
    assert renamed.json()["name"] == "重新命名"
    assert client.patch(f"/api/experiments/{first['id']}", json={"params": {}}).status_code == 422
    assert worker._claim_next_experiment() == first["id"]
    assert client.delete(f"/api/experiments/{first['id']}").status_code == 409
    worker._mark_interrupted_on_startup()
    recovered = client.get(f"/api/experiments/{first['id']}").json()
    assert recovered["status"] == "interrupted" and recovered["error"]
    retry = client.post(f"/api/experiments/{first['id']}/retry")
    assert retry.status_code == 201, retry.text
    assert retry.json()["id"] != first["id"]
    assert retry.json()["params"] == first["params"]
    assert client.delete(f"/api/experiments/{second['id']}").status_code == 200
    assert client.get(f"/api/experiments/{second['id']}").status_code == 404
    with sessions() as db:
        path = Path(db.get(Dataset, dataset_id).path)
        path.write_text("dur,proto,label\n1,tcp,0\n")
    assert worker.run_once()
    failed = client.get(f"/api/experiments/{retry.json()['id']}").json()
    assert failed["status"] == "failed" and "变化" in failed["error"]


def test_delete_success_keeps_artifact_but_hides_model(flow):
    client, sessions = flow
    dataset_id = training_dataset(client)
    experiment = submit(client, dataset_id)
    worker.run_once()
    row = client.get(f"/api/experiments/{experiment['id']}").json()
    with sessions() as db:
        path = db.get(ModelVersion, row["model_id"]).artifact_path
    assert client.delete(f"/api/experiments/{row['id']}").status_code == 200
    assert Path(path).exists()
    assert row["model_id"] not in [m["id"] for m in client.get("/api/models").json()]


@pytest.mark.parametrize("extra", [
    {"algorithm": "unknown"}, {"params": {"max_depth": -1}}, {"params": {"max_depth": True}},
    {"params": {"unknown": 1}}, {"params": {"class_weight": "wrong"}}, {"validation_fraction": .9},
    {"algorithm": "logistic_regression", "params": {"C": 0}}, {"name": "  "},
])
def test_bad_requests_are_chinese_and_not_queued(flow, extra):
    client, _ = flow
    dataset_id = training_dataset(client)
    response = client.post("/api/experiments", json={"dataset_id": dataset_id, "algorithm": "decision_tree", **extra})
    assert response.status_code == 422
    assert any('\u4e00' <= c <= '\u9fff' for c in response.json()["detail"])
    assert client.get("/api/experiments").json() == []


def test_unlabelled_dataset_cannot_train(flow):
    client, _ = flow
    dataset_id = training_dataset(client, labelled=False)
    response = client.post("/api/experiments", json={"dataset_id": dataset_id, "algorithm": "decision_tree"})
    assert response.status_code == 422 and "真实标签" in response.json()["detail"]


def test_old_database_migration_preserves_rows_and_is_repeatable(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.sqlite3'}")
    with engine.begin() as db:
        db.execute(text("CREATE TABLE experiments (id INTEGER PRIMARY KEY, dataset_id INTEGER, split_version TEXT, algorithm TEXT, params_json JSON, seed INTEGER, metrics_path TEXT, status TEXT, created_at DATETIME)"))
        db.execute(text("INSERT INTO experiments(id, algorithm, status) VALUES (1, 'decision_tree', 'failed')"))
    initialize_database(engine)
    initialize_database(engine)
    assert "metrics_json" in {c['name'] for c in inspect(engine).get_columns('experiments')}
    with engine.connect() as db:
        assert db.execute(text("SELECT algorithm, archived FROM experiments WHERE id=1")).one() == ('decision_tree', 0)
    assert (tmp_path / 'legacy-before-experiments.sqlite3').exists()
    engine.dispose()
