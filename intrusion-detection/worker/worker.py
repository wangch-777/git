"""独立任务 Worker：领取任务、执行、状态恢复。"""
from __future__ import annotations

import time
import datetime as dt
from pathlib import Path

import pandas as pd
from sqlalchemy import update

from backend.app.config import settings
from backend.app.database import SessionLocal, Base, engine, initialize_database
from backend.app.db_models import Dataset, DetectionTask, ModelVersion, Experiment
from backend.app.services.experiments import execute as execute_experiment, now
from ml.predict import predict_dataframe
from ml.registry import load_model_pack
from ml.prepare import file_sha256

# 任务状态常量
STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_INTERRUPTED = "interrupted"


def run_worker(poll_interval: float | None = None) -> None:
    """单 Worker 主循环。基础版只启用一个 Worker，简化任务抢占与 SQLite 写并发。"""
    interval = poll_interval or settings.worker_poll_interval
    initialize_database(engine)
    _mark_interrupted_on_startup()

    while True:
        if not run_once():
            time.sleep(interval)
            continue
        time.sleep(0.1)


def _mark_interrupted_on_startup() -> None:
    """重启后把遗留 running 任务标记为 interrupted，允许人工重试。"""
    with SessionLocal() as db:
        db.execute(update(DetectionTask).where(DetectionTask.status == "running").values(
            status="interrupted", error="后台重启导致任务中断，可点击重试", finished_at=dt.datetime.utcnow()))
        db.commit()
        for experiment in db.query(Experiment).filter_by(status="running").all():
            experiment.status = "interrupted"
            experiment.error = "后台重启导致训练中断，可点击重试创建新实验"
            experiment.finished_at = now()
            experiment.logs_json = [*(experiment.logs_json or []), {"time": now().isoformat(), "message": experiment.error}]
        db.commit()


def _claim_next_task():
    """从队列领取一个 queued 任务并置为 running。"""
    with SessionLocal() as db:
        task = db.query(DetectionTask).filter_by(status="queued").order_by(DetectionTask.id).first()
        if task is None:
            return None
        task_id = task.id
        claimed = db.execute(update(DetectionTask).where(
            DetectionTask.id == task_id, DetectionTask.status == "queued").values(
                status="running", started_at=dt.datetime.utcnow()))
        db.commit()
        return task_id if claimed.rowcount == 1 else None


def _execute(task_id) -> None:
    """按任务类型分发到 ml 训练或批量推理。"""
    output_dir = settings.data_processed / "detections"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"task-{task_id}.csv"
    temporary = output.with_suffix(".tmp")
    try:
        with SessionLocal() as db:
            task = db.get(DetectionTask, task_id)
            dataset = db.get(Dataset, task.dataset_id)
            model = db.get(ModelVersion, task.model_id)
            data_path, model_path = Path(dataset.path), Path(model.artifact_path)
            if file_sha256(data_path) != dataset.sha256:
                raise ValueError("数据文件内容发生变化，请重新上传")
            if file_sha256(model_path) != model.artifact_hash:
                raise ValueError("模型文件校验失败，请重新训练")
            expected_rows = task.total_rows
        pack = load_model_pack(model_path)
        processed = normal_count = attack_count = 0
        with temporary.open("w", encoding="utf-8-sig", newline="") as stream:
            for chunk in pd.read_csv(data_path, chunksize=10000):
                result = predict_dataframe(pack, chunk)
                result.to_csv(stream, index=False, header=processed == 0)
                processed += len(result)
                normal_count += int((result.predicted_label == 0).sum())
                attack_count += int((result.predicted_label == 1).sum())
                with SessionLocal() as db:
                    db.execute(update(DetectionTask).where(DetectionTask.id == task_id).values(processed_rows=processed))
                    db.commit()
        if processed != expected_rows or processed == 0 or normal_count + attack_count != processed:
            raise ValueError("处理行数与上传记录不一致")
        temporary.replace(output)
        with SessionLocal() as db:
            db.execute(update(DetectionTask).where(DetectionTask.id == task_id).values(
                status="succeeded", result_path=str(output), normal_count=normal_count,
                attack_count=attack_count, finished_at=dt.datetime.utcnow(), error=None))
            db.commit()
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        with SessionLocal() as db:
            db.execute(update(DetectionTask).where(DetectionTask.id == task_id).values(
                status="failed", error=str(exc)[:1000], finished_at=dt.datetime.utcnow()))
            db.commit()


def _claim_next_experiment():
    with SessionLocal() as db:
        record = db.query(Experiment).filter_by(status="queued", archived=False).order_by(Experiment.created_at, Experiment.id).first()
        if record is None:
            return None
        identifier = record.id
        claimed = db.execute(update(Experiment).where(Experiment.id == identifier, Experiment.status == "queued",
            Experiment.archived == False).values(status="running", started_at=now(), progress=5))
        db.commit()
        return identifier if claimed.rowcount == 1 else None


def run_once() -> bool:
    # 检测与训练共享单Worker，按创建时间选择，避免训练被检测任务持续挤占。
    with SessionLocal() as db:
        detection = db.query(DetectionTask).filter_by(status="queued").order_by(DetectionTask.created_at, DetectionTask.id).first()
        experiment = db.query(Experiment).filter_by(status="queued", archived=False).order_by(Experiment.created_at, Experiment.id).first()
        train_first = experiment is not None and (detection is None or experiment.created_at <= detection.created_at)
    if train_first:
        identifier = _claim_next_experiment()
        if identifier is None:
            return False
        execute_experiment(identifier, SessionLocal)
    else:
        identifier = _claim_next_task()
        if identifier is None:
            return False
        _execute(identifier)
    return True


if __name__ == "__main__":
    run_worker()
