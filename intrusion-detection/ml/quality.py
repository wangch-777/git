"""两阶段质量实验：先冻结验证选择，再一次性测试。python -m ml.quality --help"""
from __future__ import annotations

import argparse
import gc
import json
import platform
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.metrics import roc_curve
from sklearn.model_selection import GroupShuffleSplit

from .cli import ROOT, write_json
from .evaluate import evaluate_binary
from .features import drop_target_and_id, load_feature_schema
from .prepare import file_sha256
from .registry import load_model_pack
from .train import fit_model, save_model_pack_from_fit

SEED = 42
BASE = dict(n_estimators=80, max_depth=18, min_samples_leaf=2,
            class_weight="balanced", random_state=SEED, n_jobs=2)
# 固定候选顺序也是完全同分时的决胜规则，不能据测试成绩修改。
CANDIDATES = [
    {"id": "B", "params": BASE, "undersample": False},
    {"id": "浅树", "params": {**BASE, "max_depth": 12, "min_samples_leaf": 4}, "undersample": False},
    {"id": "深树", "params": {**BASE, "n_estimators": 120, "max_depth": 24}, "undersample": False},
    {"id": "欠采样", "params": {**BASE, "class_weight": None}, "undersample": True},
]


def split_training(frame, features):
    hashes = pd.util.hash_pandas_object(frame[features], index=False)
    unique = frame.loc[~hashes.duplicated(keep="first")]
    kept_hashes = hashes.loc[unique.index]
    ti, vi = next(GroupShuffleSplit(n_splits=1, test_size=.2, random_state=SEED)
                  .split(unique, groups=kept_hashes))
    return unique.iloc[ti], unique.iloc[vi], hashes


def undersample(frame):
    n = int(frame.label.value_counts().min())
    return pd.concat([frame.loc[frame.label == label].sample(n=n, random_state=SEED)
                      for label in (0, 1)]).sort_index()


def select_threshold(labels, scores, minimum_recall=.9):
    if not 0 < minimum_recall <= 1 or set(np.unique(labels)) != {0, 1}:
        raise ValueError("阈值选择要求两类标签和有效召回率目标")
    if not np.isfinite(scores).all():
        raise ValueError("预测分数必须为有限数值")
    fpr, recall, thresholds = roc_curve(labels, scores, drop_intermediate=False)
    valid = np.flatnonzero((recall >= minimum_recall) & np.isfinite(thresholds))
    # 最低FPR；同分取召回更高者，再取较高阈值。>=规则与检测一致。
    index = min(valid, key=lambda i: (fpr[i], -recall[i], -thresholds[i]))
    return float(thresholds[index]), pd.DataFrame({"threshold": thresholds[1:],
                                                  "recall": recall[1:], "fpr": fpr[1:]})


def choose_candidate(results):
    return max(results, key=lambda item: (item["validation"]["f1"], item["validation"]["ap"]))


def metrics(labels, probabilities, threshold):
    return evaluate_binary(labels, (probabilities >= threshold).astype(int), probabilities)


def verify(path, digest):
    if not path.exists() or file_sha256(path) != digest:
        raise ValueError(f"文件缺失或摘要发生变化：{path.name}")


def prepare(output):
    # 目录排他创建，防止覆盖一次已经查看测试成绩的实验。
    output.mkdir(parents=True, exist_ok=False)
    source = json.loads((ROOT / "configs/dataset_source.json").read_text(encoding="utf-8"))
    train_path = ROOT / "data/raw/UNSW_NB15_training-set.csv"
    verify(train_path, source["files"][train_path.name]["sha256"])
    plan = {"seed": SEED, "validation_fraction": .2, "minimum_recall": .9,
            "candidates": CANDIDATES, "source": source,
            "selection": "验证阈值0.5的F1最高，AP决胜，再按候选顺序；阈值以召回>=0.9最小化FPR",
            "test_policy": "选择冻结后统一评估B、欠采样、最终模型；C仅使用相同预测的非重叠子集",
            "environment": {"python": platform.python_version(), "sklearn": sklearn.__version__,
                            "pandas": pd.__version__, "numpy": np.__version__, "platform": platform.platform()},
            "code_hash": file_sha256(Path(__file__))}
    write_json(output / "plan.json", plan)
    frame = pd.read_csv(train_path)
    features = drop_target_and_id(frame).columns.tolist()
    schema = load_feature_schema(ROOT / "configs/feature_schema.json")
    if set(features) != set(schema["numeric"] + schema["categorical"]):
        raise ValueError("特征协议不一致")
    train, val, hashes = split_training(frame, features)
    if any(set(part.label.unique()) != {0, 1} for part in (train, val)):
        raise ValueError("划分必须包含两类")
    label_variants = frame.groupby(hashes).label.nunique()
    split = {"train_indices": train.index.tolist(), "validation_indices": val.index.tolist(),
             "train_rows": len(train), "validation_rows": len(val), "original_rows": len(frame),
             "removed_rows": int(hashes.duplicated().sum()),
             "conflicting_label_groups": int((label_variants > 1).sum())}
    write_json(output / "split.json", split)
    results = []
    for candidate in CANDIDATES:
        fit = undersample(train) if candidate["undersample"] else train
        started = time.perf_counter()
        print(f"训练 {candidate['id']}：{len(fit)}条", flush=True)
        pipe = fit_model(fit[features], fit.label, "random_forest", candidate["params"],
                         schema["numeric"], schema["categorical"])
        seconds = time.perf_counter() - started
        probability = pipe.predict_proba(val[features])[:, list(pipe.classes_).index(1)]
        threshold, curve = select_threshold(val.label, probability, plan["minimum_recall"])
        directory = output / candidate["id"]
        model = Path(save_model_pack_from_fit(pipe, features, {"0": "正常", "1": "攻击"}, threshold,
                     directory, {"name": "model", "params": candidate["params"], "seed": SEED,
                     "training_hash": source["files"][train_path.name]["sha256"],
                     "threshold_policy": plan["selection"]}))
        pd.DataFrame({"source_index": val.index, "label": val.label, "probability": probability}).to_csv(
            directory / "validation.csv", index=False)
        curve.to_csv(directory / "recall-fpr.csv", index=False)
        item = {**candidate, "train_rows": len(fit), "train_seconds": seconds,
                "validation": metrics(val.label, probability, .5), "threshold": threshold,
                "validation_tuned": metrics(val.label, probability, threshold),
                "model": str(model.relative_to(output)), "model_hash": file_sha256(model),
                "meta_hash": file_sha256(model.with_suffix(".pack_meta.json"))}
        results.append(item)
        write_json(output / "search.json", results)
        del pipe
        gc.collect()
    chosen = choose_candidate(results)
    # 冻结文件在任何测试数据读取前写入；模型、元信息及划分均绑定摘要。
    freeze = {"selected_id": chosen["id"], "threshold": chosen["threshold"], "candidates": results,
              "plan_hash": file_sha256(output / "plan.json"), "split_hash": file_sha256(output / "split.json")}
    write_json(output / "frozen.json", freeze)
    print(f"验证选择已冻结：{chosen['id']}，阈值{chosen['threshold']:.9f}；尚未读取测试数据", flush=True)


def probabilities(pack, frame):
    features = pack["meta"]["feature_list"]
    positive = list(pack["classifier"].classes_).index(1)
    return np.concatenate([pack["classifier"].predict_proba(pack["preprocessor"].transform(
        frame.iloc[start:start + 10000][features]))[:, positive] for start in range(0, len(frame), 10000)])


def finalize(output):
    if (output / "test-started.json").exists():
        raise ValueError("此实验已开始过最终测试，拒绝重复评估或覆盖成绩")
    freeze = json.loads((output / "frozen.json").read_text(encoding="utf-8"))
    verify(output / "plan.json", freeze["plan_hash"])
    verify(output / "split.json", freeze["split_hash"])
    plan = json.loads((output / "plan.json").read_text(encoding="utf-8"))
    verify(Path(__file__), plan["code_hash"])
    for item in freeze["candidates"]:
        verify(output / item["model"], item["model_hash"])
        verify((output / item["model"]).with_suffix(".pack_meta.json"), item["meta_hash"])
    # x模式抢占：第二进程也不能重复启动测试。
    with (output / "test-started.json").open("x", encoding="utf-8") as stream:
        json.dump({"frozen_hash": file_sha256(output / "frozen.json"), "started_at": time.time()}, stream)
    paths = [ROOT / "data/raw" / name for name in plan["source"]["files"]]
    for path in paths:
        verify(path, plan["source"]["files"][path.name]["sha256"])
    train = pd.read_csv(ROOT / "data/raw/UNSW_NB15_training-set.csv")
    test = pd.read_csv(ROOT / "data/raw/UNSW_NB15_testing-set.csv")
    features = drop_target_and_id(train).columns.tolist()
    train_hashes = pd.util.hash_pandas_object(train[features], index=False)
    keep = ~pd.util.hash_pandas_object(test[features], index=False).isin(train_hashes)
    baseline_dir = ROOT / "artifacts/baseline"
    baseline = json.loads((baseline_dir / "summary.json").read_text(encoding="utf-8"))
    basepack = load_model_pack(baseline_dir / "random_forest.pack_joblib")
    verify(baseline_dir / "random_forest.pack_joblib", basepack["meta"]["artifact_hash"])
    if basepack["meta"]["source"]["files"] != plan["source"]["files"] or baseline["params"] != BASE:
        raise ValueError("可复用的基线与当前协议不一致")
    base_scores = probabilities(basepack, test)
    baseline_check = metrics(test.label, base_scores, .5)
    if any(not np.isclose(value, baseline["metrics"]["test"][key], atol=1e-10) for key, value in baseline_check.items()):
        raise ValueError("基线摘要与模型不一致，不能复用")
    output_metrics = {"A": {"validation": baseline["metrics"]["validation"],
                            "test": baseline["metrics"]["test"], "train_rows": baseline["train_rows"]},
                      "C_A": metrics(test.label[keep], base_scores[keep], .5)}
    del basepack
    gc.collect()
    for item in freeze["candidates"]:
        if item["id"] not in {"B", "欠采样", freeze["selected_id"]}:
            continue
        pack = load_model_pack(output / item["model"])
        scores = probabilities(pack, test)
        pd.DataFrame({"label": test.label, "probability": scores, "nonoverlap": keep}).to_csv(
            output / item["id"] / "test-predictions.csv", index=False)
        output_metrics[item["id"]] = {"validation": item["validation"], "test": metrics(test.label, scores, .5)}
        if item["id"] == "B":
            output_metrics["C_B"] = metrics(test.label[keep], scores[keep], .5)
        if item["id"] == freeze["selected_id"]:
            output_metrics["selected"] = {"id": item["id"], "threshold": freeze["threshold"],
                "validation": item["validation_tuned"], "test": metrics(test.label, scores, freeze["threshold"])}
        del pack
        gc.collect()
    result = {"metrics": output_metrics, "test_rows": len(test), "diagnostic_rows": int(keep.sum()),
              "overlap_removed": int((~keep).sum()), "environment": plan["environment"],
              "frozen_hash": file_sha256(output / "frozen.json"),
              "baseline_summary_hash": file_sha256(baseline_dir / "summary.json")}
    write_json(output / "results.json", result)
    print("一次性最终评估已保存：" + str(output / "results.json"), flush=True)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="去重分析与仅验证集选参：先prepare，再finalize")
    parser.add_argument("phase", choices=["prepare", "finalize"])
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/quality-02")
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / "artifacts").resolve()):
        parser.error("产物必须位于artifacts目录内")
    try:
        (prepare if args.phase == "prepare" else finalize)(output)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"错误：{exc}\n")


if __name__ == "__main__":
    main()
