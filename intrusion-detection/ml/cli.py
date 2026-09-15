"""Reproducible local baseline and CSV prediction: python -m ml.cli --help."""
from __future__ import annotations

import argparse
import csv
import json
import platform
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

from .evaluate import evaluate_binary
from .features import drop_target_and_id, load_feature_schema
from .predict import predict_dataframe
from .prepare import audit, file_sha256
from .registry import load_model_pack
from .train import fit_model, save_model_pack_from_fit

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw"
OUT = ROOT / "artifacts/baseline"


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def download_data():
    source = json.loads((ROOT / "configs/dataset_source.json").read_text(encoding="utf-8"))
    RAW.mkdir(parents=True, exist_ok=True)
    for name, expected in source["files"].items():
        dest = RAW / name
        if not dest.exists():
            temporary = dest.with_suffix(".download")
            print(f"Downloading {name}", flush=True)
            urllib.request.urlretrieve(source["mirror_base"] + name, temporary)
            if file_sha256(temporary) != expected["sha256"]:
                raise ValueError(f"下载校验失败: {name}")
            temporary.replace(dest)
        if file_sha256(dest) != expected["sha256"]:
            raise ValueError(f"文件摘要与记录不符，请检查来源: {name}")
        df = pd.read_csv(dest)
        if len(df) != expected["rows"] or len(df.columns) != 45:
            raise ValueError(f"文件行列数量不符: {name}")
        print(f"Verified {name}: {len(df)} rows, 45 columns", flush=True)
    return source


def check_header(path):
    with open(path, encoding="utf-8-sig", newline="") as stream:
        header = next(csv.reader(stream), [])
    if len(header) != len(set(header)):
        raise ValueError("CSV 含重复列名")


def predict_csv(model_path, input_path, output_path):
    """Write UTF-8 BOM CSV that Excel can open with Chinese labels."""
    check_header(input_path)
    pack = load_model_pack(model_path)
    output_path = Path(output_path)
    if output_path.resolve() == Path(input_path).resolve():
        raise ValueError("输出文件不能覆盖输入文件")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    total = 0
    counts = {}
    try:
        with temporary.open("w", encoding="utf-8-sig", newline="") as stream:
            for chunk in pd.read_csv(input_path, chunksize=10000):
                if chunk.empty:
                    continue
                result = predict_dataframe(pack, chunk)
                result.to_csv(stream, index=False, header=total == 0)
                total += len(result)
                for name, count in result.predicted_name.value_counts().items():
                    counts[name] = counts.get(name, 0) + int(count)
        if not total:
            raise ValueError("CSV 没有数据行")
        temporary.replace(output_path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    print(json.dumps({"rows": total, "predictions": counts, "output": str(output_path)}, ensure_ascii=False))
    return total


def baseline():
    source = download_data()
    train_path = RAW / "UNSW_NB15_training-set.csv"
    test_path = RAW / "UNSW_NB15_testing-set.csv"
    full_train, test = pd.read_csv(train_path), pd.read_csv(test_path)
    features = drop_target_and_id(full_train).columns.tolist()
    schema = load_feature_schema(ROOT / "configs/feature_schema.json")
    if set(features) != set(schema["numeric"] + schema["categorical"]):
        raise ValueError("下载数据的特征与协议不一致")
    # Identical feature rows stay in the same training/validation group.
    groups = pd.util.hash_pandas_object(full_train[features], index=False)
    train_idx, val_idx = next(GroupShuffleSplit(n_splits=1, test_size=.2, random_state=42)
                             .split(full_train, groups=groups))
    train, val = full_train.iloc[train_idx], full_train.iloc[val_idx]
    for frame in (train, val, test):
        if set(frame.label.unique()) != {0, 1}:
            raise ValueError("每个划分必须含正常和攻击两类")
    quality = {"source": source, "training": audit(full_train), "testing": audit(test),
               "duplicate_feature_rows_train": int(groups.duplicated().sum()),
               "test_feature_rows_also_in_training": int(pd.util.hash_pandas_object(test[features], index=False).isin(groups).sum()),
               "train_validation_overlap": int(len(set(groups.iloc[train_idx]) & set(groups.iloc[val_idx]))),
               "train_label_counts": full_train.label.value_counts().to_dict(),
               "test_label_counts": test.label.value_counts().to_dict()}
    write_json(OUT / "data_quality.json", quality)
    params = {"n_estimators": 80, "max_depth": 18, "min_samples_leaf": 2,
              "class_weight": "balanced", "random_state": 42, "n_jobs": 2}
    print(f"Training random forest on {len(train)} rows / {len(features)} features...", flush=True)
    started = time.perf_counter()
    pipe = fit_model(train[features], train.label, "random_forest", params,
                     schema["numeric"], schema["categorical"])
    train_seconds = time.perf_counter() - started
    model_path = save_model_pack_from_fit(pipe, features, {"0": "正常", "1": "攻击"}, .5, OUT,
        {"name": "random_forest", "algorithm": "random_forest", "params": params,
         "source": source, "training_rows": len(train), "validation_rows": len(val),
         "split": "GroupShuffleSplit on feature hashes, seed=42, validation groups=20%",
         "threshold_policy": "fixed 0.5; no test-driven tuning"})
    metrics = {}
    for name, frame in (("validation", val), ("test", test)):
        started = time.perf_counter()
        probability = pipe.predict_proba(frame[features])[:, list(pipe.classes_).index(1)]
        seconds = time.perf_counter() - started
        metrics[name] = {**evaluate_binary(frame.label, (probability >= .5).astype(int), probability),
                         "rows": len(frame), "inference_seconds": seconds}
    summary = {"algorithm": "RandomForest", "feature_count": len(features), "params": params,
               "train_rows": len(train), "validation_rows": len(val), "test_rows": len(test),
               "train_seconds": train_seconds, "metrics": metrics,
               "environment": {"platform": platform.platform(), "processor": platform.processor()},
               "model_path": str(Path(model_path).relative_to(ROOT)),
               "limitations": f"公开镜像数据的固定基线实验，未调参。原测试文件中有{quality['test_feature_rows_also_in_training']}条特征记录也出现在原训练文件，指标不代表无重复的泛化效果或真实网络效果。"}
    write_json(OUT / "summary.json", summary)
    # Export a small unlabelled demonstration input, never used for training.
    sample = test.sample(n=min(100, len(test)), random_state=42)
    sample[features].to_csv(ROOT / "data/processed/demo_input.csv", index=False, encoding="utf-8-sig")
    sample[["id", "label", "attack_cat"]].reset_index(drop=True).to_csv(
        ROOT / "data/processed/demo_truth.csv", index=False, encoding="utf-8-sig")
    predict_csv(model_path, ROOT / "data/processed/demo_input.csv", ROOT / "data/processed/demo_predictions.csv")
    predict_csv(model_path, test_path, ROOT / "data/processed/test_predictions.csv")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    export_evaluation()


def export_evaluation():
    from .visual_evaluation import chart_metrics
    model = OUT / "random_forest.pack_joblib"
    source = RAW / "UNSW_NB15_testing-set.csv"
    pack = load_model_pack(model)
    if file_sha256(model) != pack["meta"]["artifact_hash"]:
        raise ValueError("模型校验失败")
    expected = pack["meta"]["source"]["files"][source.name]["sha256"]
    if file_sha256(source) != expected:
        raise ValueError("测试文件与训练记录中的数据版本不一致")
    frame = pd.read_csv(source)
    X = frame[pack["meta"]["feature_list"]]
    probability = pack["classifier"].predict_proba(pack["preprocessor"].transform(X))[:, 1]
    cutoff = pack["meta"]["threshold"]
    result = chart_metrics(frame.label, (probability >= cutoff).astype(int), probability)
    summary = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    result.update(rows=len(frame), threshold=cutoff, model_hash=file_sha256(model),
                  meta_hash=file_sha256(model.with_suffix(".pack_meta.json")),
                  test_hash=expected, limitations=summary["limitations"])
    write_json(OUT / "evaluation.json", result)
    print("Evaluation charts saved: artifacts/baseline/evaluation.json")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="本地入侵检测：下载、训练及CSV预测")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("download", help="下载并验证已记录的公开镜像")
    commands.add_parser("baseline", help="训练固定随机森林并评价验证集和测试集")
    commands.add_parser("evaluate", help="为现有基础模型生成评价图表数据，不重新训练")
    prediction = commands.add_parser("predict", help="对兼容CSV输出正常/攻击")
    prediction.add_argument("--model", type=Path, default=OUT / "random_forest.pack_joblib")
    prediction.add_argument("--input", type=Path, required=True)
    prediction.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "download":
            download_data()
        elif args.command == "baseline":
            baseline()
        elif args.command == "evaluate":
            export_evaluation()
        else:
            predict_csv(args.model, args.input, args.output)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"错误: {exc}\n")


if __name__ == "__main__":
    main()
