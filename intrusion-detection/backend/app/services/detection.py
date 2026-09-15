"""Local dataset validation, immutable model registration and result queries."""
import json
import shutil
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd
from fastapi import HTTPException
from sqlalchemy.orm import Session

from ml.cli import check_header
from ml.features import load_feature_schema
from ml.prepare import file_sha256
from ..config import settings
from ..db_models import Dataset, DetectionTask, ModelVersion

MAX_BYTES = 50 * 1024 * 1024
MAX_ROWS = 300_000


def inspect_csv(path: Path) -> tuple[int, bool]:
    check_header(path)
    schema = load_feature_schema(settings.configs / "feature_schema.json")
    required = schema["numeric"] + schema["categorical"]
    count, has_label = 0, False
    for chunk in pd.read_csv(path, chunksize=10000):
        missing = [col for col in required if col not in chunk.columns]
        if missing:
            raise ValueError("缺少必需字段：" + ", ".join(missing))
        for col in schema["numeric"]:
            try:
                values = pd.to_numeric(chunk[col], errors="raise")
            except (ValueError, TypeError) as exc:
                raise ValueError(f"字段 {col} 含非数值内容") from exc
            if np.isinf(values.to_numpy(dtype=float)).any():
                raise ValueError(f"字段 {col} 含无穷值")
        count += len(chunk)
        if count > MAX_ROWS:
            raise ValueError("当前版本最多支持300,000行，请拆分文件")
        has_label = "label" in chunk.columns
    if count == 0:
        raise ValueError("CSV没有数据行")
    return count, has_label


def register_dataset(path: Path, name: str, db: Session) -> Dataset:
    try:
        rows, labels = inspect_csv(path)
        dataset = Dataset(name=name, path=str(path), sha256=file_sha256(path),
                          schema_version="unsw-42-v1", row_count=rows, label_available=labels)
        db.add(dataset)
        db.commit()
        db.refresh(dataset)
        return dataset
    except (ValueError, UnicodeError, pd.errors.ParserError) as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(422, str(exc)) from exc


def new_upload_path() -> Path:
    directory = settings.data_raw / "uploads"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{uuid4().hex}.csv"


def register_baseline(db: Session):
    source = settings.artifacts / "baseline/random_forest.pack_joblib"
    if not source.exists():
        return
    meta_path = source.with_suffix(".pack_meta.json")
    if not meta_path.exists():
        return
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    digest = file_sha256(source)
    if digest != meta.get("artifact_hash"):
        raise HTTPException(409, "基础模型文件校验失败，请重新训练")
    # Freeze artifacts so later CLI training cannot change queued task models.
    version_key = file_sha256(meta_path)
    dest = settings.artifacts / "registered" / version_key / source.name
    existing = db.query(ModelVersion).filter_by(artifact_path=str(dest)).first()
    if existing:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    shutil.copy2(meta_path, dest.with_suffix(".pack_meta.json"))
    db.add(ModelVersion(artifact_path=str(dest), artifact_hash=digest,
                        feature_schema={"features": meta["feature_list"]},
                        label_map=meta["label_map"], threshold=meta["threshold"],
                        dependency_versions=meta["dependency_versions"]))
    db.commit()


def task_or_404(db, task_id):
    task = db.get(DetectionTask, task_id)
    if task is None:
        raise HTTPException(404, "检测任务不存在")
    return task


def completed_task(db, task_id):
    task = task_or_404(db, task_id)
    if task.status != "succeeded" or not task.result_path:
        raise HTTPException(409, "任务尚未成功完成，暂无结果")
    return task


def result_path(task):
    path = Path(task.result_path)
    if not path.exists():
        raise HTTPException(410, "结果文件已不存在，请重新检测")
    return path


RESULT_CHUNK_ROWS = 10000


def result_counts(db, task):
    """旧任务首次分块回填；NULL表示未知，0表示已知的零。"""
    if task.normal_count is not None and task.attack_count is not None:
        return task.normal_count, task.attack_count
    normal = attack = 0
    with pd.read_csv(result_path(task), usecols=["predicted_label"], chunksize=RESULT_CHUNK_ROWS) as chunks:
        for chunk in chunks:
            normal += int((chunk.predicted_label == 0).sum())
            attack += int((chunk.predicted_label == 1).sum())
    task.normal_count, task.attack_count = normal, attack
    db.commit()
    return normal, attack


def statistics(normal, attack, label=None):
    normal = normal if label != 1 else 0
    attack = attack if label != 0 else 0
    total = normal + attack
    return {"total": total, "attack": attack, "normal": normal,
            "attack_ratio": attack / total if total else 0}


def result_page(path, total, page, page_size, label=None):
    start = (page - 1) * page_size
    if start >= total:
        return {"total": total, "items": []}
    if label is None:
        # callable避免构造与页偏移一样大的skiprows集合；仍需扫描前缀。
        frame = pd.read_csv(path, skiprows=lambda row: 0 < row <= start, nrows=page_size)
        return {"total": total, "items": frame.to_dict(orient="records")}
    matched, items = 0, []
    with pd.read_csv(path, chunksize=RESULT_CHUNK_ROWS) as chunks:
        for chunk in chunks:
            selected = chunk.loc[chunk.predicted_label == label]
            offset = max(0, start - matched)
            if offset < len(selected):
                items.extend(selected.iloc[offset:offset + page_size - len(items)].to_dict(orient="records"))
            matched += len(selected)
            if len(items) == page_size:
                break
    return {"total": total, "items": items}


def stream_result(path, label=None):
    if label is None:
        # Worker生成的文件已有且仅有一次UTF-8 BOM，原样传输。
        with path.open("rb") as source:
            while block := source.read(65536):
                yield block
        return
    yield b"\xef\xbb\xbf"
    first = True
    with pd.read_csv(path, chunksize=RESULT_CHUNK_ROWS) as chunks:
        for chunk in chunks:
            selected = chunk.loc[chunk.predicted_label == label]
            if first or not selected.empty:
                yield selected.to_csv(index=False, header=first).encode("utf-8")
                first = False
