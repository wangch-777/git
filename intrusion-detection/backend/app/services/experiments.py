"""可追溯的二分类训练与验证；固定分组划分，不使用测试集调参。"""
import datetime as dt
import hashlib
import json
import logging
import math
import time
import warnings
from pathlib import Path

import pandas as pd
from fastapi import HTTPException
from sklearn.exceptions import ConvergenceWarning
from sklearn.model_selection import GroupShuffleSplit, train_test_split

from ml.features import TARGET_COLUMNS, load_feature_schema
from ml.prepare import file_sha256
from ml.train import fit_model, save_model_pack_from_fit
from ml.visual_evaluation import chart_metrics
from ..config import settings
from ..db_models import Dataset, Experiment, ModelVersion
from .detection import new_upload_path, register_dataset

ALGORITHMS = {"logistic_regression": "逻辑回归", "decision_tree": "决策树", "random_forest": "随机森林"}


def now():
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def parameters(algorithm, supplied, seed):
    if algorithm not in ALGORITHMS:
        raise HTTPException(422, "请选择逻辑回归、决策树或随机森林")
    defaults = ({"C": 1.0, "max_iter": 1000} if algorithm == "logistic_regression"
                else {"max_depth": 18, "min_samples_leaf": 2})
    if algorithm == "random_forest":
        defaults["n_estimators"] = 80
    defaults["class_weight"] = "balanced"
    if set(supplied) - set(defaults):
        raise HTTPException(422, "包含不支持的超参数，请检查表单")
    result = {**defaults, **supplied}
    bounds = {"max_iter": (100, 5000), "max_depth": (1, 40), "min_samples_leaf": (1, 50), "n_estimators": (10, 300)}
    for key, (low, high) in bounds.items():
        if key not in result or key == "max_depth" and result[key] is None:
            continue
        value = result[key]
        if type(value) is not int or not low <= value <= high:
            raise HTTPException(422, f"参数 {key} 必须是{low}到{high}之间的整数")
    if "C" in result and (type(result["C"]) not in (int, float) or not math.isfinite(result["C"]) or not .001 <= result["C"] <= 100):
        raise HTTPException(422, "正则化参数必须在0.001到100之间")
    if result["class_weight"] not in (None, "balanced"):
        raise HTTPException(422, "类别权重只能选择平衡或不加权")
    result["random_state"] = seed
    if algorithm == "random_forest":
        result["n_jobs"] = 2
    return result


def find_experiment(db, experiment_id):
    record = db.get(Experiment, experiment_id)
    if record is None or record.archived:
        raise HTTPException(404, "实验不存在或已删除")
    return record


def serialize(db, record):
    dataset = db.get(Dataset, record.dataset_id)
    model = db.query(ModelVersion).filter_by(experiment_id=record.id, enabled=True).first()
    comparison = json.dumps([record.dataset_hash, record.seed, record.validation_fraction,
                             record.split_version, record.feature_schema_json], sort_keys=True)
    return {"id": record.id, "name": record.name, "algorithm": record.algorithm,
            "algorithm_name": ALGORITHMS.get(record.algorithm, "未知算法"),
            "params": record.params_json, "dataset_id": record.dataset_id,
            "dataset_name": dataset.name if dataset else "数据已不存在", "dataset_hash": record.dataset_hash,
            "seed": record.seed, "validation_fraction": record.validation_fraction,
            "train_rows": record.train_rows, "validation_rows": record.validation_rows,
            "train_seconds": record.train_seconds, "metrics": record.metrics_json,
            "status": record.status, "progress": record.progress or 0, "logs": record.logs_json or [],
            "error": record.error, "created_at": record.created_at, "started_at": record.started_at,
            "finished_at": record.finished_at, "model_id": model.id if model else None,
            "comparison_key": hashlib.sha256(comparison.encode()).hexdigest()}


def create(db, payload):
    dataset = db.get(Dataset, payload.dataset_id)
    if dataset is None:
        raise HTTPException(404, "数据集不存在")
    if not dataset.label_available:
        raise HTTPException(422, "训练需要包含真实标签label的数据，请使用训练示例或上传带标签CSV")
    if not Path(dataset.path).exists():
        raise HTTPException(409, "数据文件不存在，请重新导入")
    params = parameters(payload.algorithm, payload.params, payload.seed)
    if not payload.name.strip():
        raise HTTPException(422, "实验名称不能为空")
    record = Experiment(name=payload.name.strip(), dataset_id=dataset.id, dataset_hash=dataset.sha256,
                        algorithm=payload.algorithm, params_json=params, seed=payload.seed,
                        validation_fraction=payload.validation_fraction, split_version="特征分组划分-v1",
                        feature_schema_json=load_feature_schema(settings.configs / "feature_schema.json"),
                        status="queued", progress=0, logs_json=[{"time": now().isoformat(), "message": "实验已创建，等待后台训练"}])
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def sample_dataset(db):
    path = settings.data_raw / "UNSW_NB15_training-set.csv"
    manifest_path = settings.configs / "dataset_source.json"
    if not path.exists() or not manifest_path.exists():
        raise HTTPException(404, "训练源数据尚未准备，请先下载基础数据集")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if file_sha256(path) != manifest["files"][path.name]["sha256"]:
        raise HTTPException(409, "训练源文件校验失败，请重新下载")
    frame = pd.read_csv(path)
    if len(frame) > 2000:
        frame, _ = train_test_split(frame, train_size=2000, stratify=frame.label, random_state=42)
    destination = new_upload_path()
    frame.to_csv(destination, index=False, encoding="utf-8-sig")
    digest = file_sha256(destination)
    existing = db.query(Dataset).filter_by(sha256=digest).first()
    if existing and Path(existing.path).exists():
        destination.unlink()
        return existing
    return register_dataset(destination, "训练示例（来自原训练文件，2000条）.csv", db)


def stage(sessions, experiment_id, progress, message, **fields):
    with sessions() as db:
        record = db.get(Experiment, experiment_id)
        record.progress = progress
        record.logs_json = [*(record.logs_json or []), {"time": now().isoformat(), "message": message}]
        for key, value in fields.items():
            setattr(record, key, value)
        db.commit()


class TrainingDataError(ValueError):
    pass


def execute(experiment_id, sessions):
    try:
        stage(sessions, experiment_id, 10, "读取数据并核验文件摘要")
        with sessions() as db:
            record = db.get(Experiment, experiment_id)
            dataset = db.get(Dataset, record.dataset_id)
            path = Path(dataset.path)
            config = {"algorithm": record.algorithm, "params": record.params_json, "seed": record.seed,
                      "ratio": record.validation_fraction, "schema": record.feature_schema_json,
                      "dataset_hash": record.dataset_hash, "dataset_id": dataset.id}
        if not path.exists() or file_sha256(path) != config["dataset_hash"]:
            raise TrainingDataError("数据文件缺失或内容发生变化，请重新导入后新建实验")
        frame = pd.read_csv(path)
        if "label" not in frame or frame.label.isna().any() or set(frame.label.unique()) != {0, 1}:
            raise TrainingDataError("真实标签label必须包含正常0和攻击1两类，且不能缺失")
        if len(frame) < 20 or frame.label.value_counts().min() < 5:
            raise TrainingDataError("训练至少需要20条数据，且正常和攻击各不少于5条")
        schema = config["schema"]
        features = [c for c in schema["numeric"] + schema["categorical"] if c not in TARGET_COLUMNS]
        if any(c not in frame for c in features):
            raise TrainingDataError("数据缺少特征字段，请按训练协议重新导入")
        groups = pd.util.hash_pandas_object(frame[features], index=False)
        try:
            train_idx, val_idx = next(GroupShuffleSplit(n_splits=1, test_size=config["ratio"], random_state=config["seed"])
                                      .split(frame, groups=groups))
        except ValueError as exc:
            raise TrainingDataError("不同特征样本太少，无法划分训练和验证数据") from exc
        train, val = frame.iloc[train_idx], frame.iloc[val_idx]
        if any(set(part.label.unique()) != {0, 1} for part in (train, val)):
            raise TrainingDataError("分组划分后缺少某个类别，请增加样本或调整随机种子")
        output = settings.artifacts / "experiments" / str(experiment_id)
        output.mkdir(parents=True, exist_ok=True)
        # Record original CSV row indices, so the partition can be audited exactly.
        split = {"train_rows": train_idx.tolist(), "validation_rows": val_idx.tolist(),
                 "dataset_hash": config["dataset_hash"], "seed": config["seed"], "validation_fraction": config["ratio"]}
        (output / "split.json").write_text(json.dumps(split), encoding="utf-8")
        stage(sessions, experiment_id, 25, f"完成分组划分：训练{len(train)}条，验证{len(val)}条；重复特征不会跨组",
              train_rows=len(train), validation_rows=len(val))
        stage(sessions, experiment_id, 40, "正在拟合预处理和分类模型，此阶段可能较久；进度表示处理阶段")
        started = time.perf_counter()
        with warnings.catch_warnings(record=True) as recorded:
            warnings.simplefilter("always", ConvergenceWarning)
            pipe = fit_model(train[features], train.label, config["algorithm"], config["params"], schema["numeric"], schema["categorical"])
        seconds = time.perf_counter() - started
        if any(issubclass(w.category, ConvergenceWarning) for w in recorded):
            stage(sessions, experiment_id, 75, "模型达到迭代上限仍未完全收敛，可增加迭代次数后新建实验")
        stage(sessions, experiment_id, 80, "训练完成，正在验证集计算指标", train_seconds=seconds)
        probability = pipe.predict_proba(val[features])[:, list(pipe.classes_).index(1)]
        evaluation = chart_metrics(val.label, (probability >= .5).astype(int), probability)
        evaluation.update(train_rows=len(train), validation_rows=len(val), train_seconds=seconds,
                          dataset_hash=config["dataset_hash"], threshold=.5, evaluation_scope="验证集")
        metrics_path = output / "metrics.json"
        metrics_path.write_text(json.dumps(evaluation, ensure_ascii=False, indent=2), encoding="utf-8")
        stage(sessions, experiment_id, 95, "保存模型、参数、数据版本和验证结果")
        model_path = Path(save_model_pack_from_fit(pipe, features, {"0": "正常", "1": "攻击"}, .5, output,
            {"name": "model", "algorithm": config["algorithm"], "params": config["params"],
             "experiment_id": experiment_id, "dataset_id": config["dataset_id"], "dataset_hash": config["dataset_hash"],
             "seed": config["seed"], "validation_fraction": config["ratio"], "train_rows": len(train), "validation_rows": len(val)}))
        meta = json.loads(model_path.with_suffix(".pack_meta.json").read_text(encoding="utf-8"))
        with sessions() as db:
            record = db.get(Experiment, experiment_id)
            db.add(ModelVersion(experiment_id=experiment_id, artifact_path=str(model_path),
                                artifact_hash=meta["artifact_hash"], feature_schema={"features": features},
                                label_map=meta["label_map"], threshold=.5, dependency_versions=meta["dependency_versions"]))
            record.metrics_path = str(metrics_path)
            record.metrics_json = evaluation["metrics"]
            record.status, record.progress, record.finished_at = "succeeded", 100, now()
            record.logs_json = [*(record.logs_json or []), {"time": now().isoformat(), "message": "实验成功，模型已可用于批量检测"}]
            db.commit()
    except Exception as exc:
        logging.getLogger(__name__).exception("训练实验%s失败", experiment_id)
        message = str(exc) if isinstance(exc, TrainingDataError) else "训练失败，请检查数据格式与参数；详细原因已写入后台日志"
        stage(sessions, experiment_id, 0, message, status="failed", error=message, finished_at=now())
