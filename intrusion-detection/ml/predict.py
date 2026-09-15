"""批量推理：分块处理大文件，逐行预测并输出结果。

逐行预测保存为 Parquet，包含 task_id、source_row_id、predicted_label、
score 与可选 true_label；原始特征通过文件与行号追溯。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .features import drop_target_and_id
from .registry import load_model_pack


def predict_dataframe(
    model_pack: dict,
    df: pd.DataFrame,
) -> pd.DataFrame:
    """对整个 DataFrame 批量预测，返回 source_row_id/predicted_label/score。"""
    feature_list = model_pack["meta"]["feature_list"]
    label_map = model_pack["meta"]["label_map"]
    threshold = model_pack["meta"]["threshold"]

    if df.empty:
        raise ValueError("CSV 没有数据行")
    if df.columns.duplicated().any():
        raise ValueError("CSV 含重复列名")
    missing = [c for c in feature_list if c not in df.columns]
    if missing:
        raise ValueError(f"缺少模型必需字段: {', '.join(missing)}")
    X = drop_target_and_id(df).loc[:, feature_list].copy()
    for name, _, columns in model_pack["preprocessor"].transformers_:
        if name == "num":
            for col in columns:
                try:
                    X[col] = pd.to_numeric(X[col], errors="raise")
                except (ValueError, TypeError) as exc:
                    raise ValueError(f"字段 {col} 必须是数值") from exc
            if np.isinf(X[columns].to_numpy(dtype=float)).any():
                raise ValueError("数值字段含无穷值")
    proba = model_pack["classifier"].predict_proba(
        model_pack["preprocessor"].transform(X)
    )
    classes = model_pack["classifier"].classes_
    if len(classes) == 2 and set(classes) == {0, 1}:
        cutoff = threshold if threshold is not None else 0.5
        if not 0 <= cutoff <= 1:
            raise ValueError("阈值必须在 0 到 1 之间")
        attack_index = int(np.flatnonzero(classes == 1)[0])
        predicted = (proba[:, attack_index] >= cutoff).astype(int)
        pred_idx = np.array([int(np.flatnonzero(classes == p)[0]) for p in predicted])
    else:
        pred_idx = np.argmax(proba, axis=1)
        predicted = classes[pred_idx]
    score = proba[np.arange(len(df)), pred_idx]

    return pd.DataFrame(
        {
            "source_row_id": df.index.astype(str),
            "predicted_label": predicted,
            "predicted_name": [label_map.get(str(p), str(p)) for p in predicted],
            "score": score,
        }
    )


def predict_batch_to_parquet(
    model_pack_path: str | Path,
    csv_path: str | Path,
    out_path: str | Path,
    chunk_size: int = 50_000,
) -> pd.DataFrame:
    """分块读取 CSV 并逐块推理，写入单个 Parquet。"""
    model_pack = load_model_pack(model_pack_path)
    chunks = pd.read_csv(csv_path, chunksize=chunk_size)
    results = []
    for chunk in chunks:
        results.append(predict_dataframe(model_pack, chunk))
    out = pd.concat(results, ignore_index=True)
    out.to_parquet(out_path, index=False)
    return out


def _is_multiclass(proba: np.ndarray) -> bool:
    return proba.shape[1] > 2
