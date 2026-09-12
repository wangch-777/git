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

    X = drop_target_and_id(df).reindex(columns=feature_list)
    proba = model_pack["classifier"].predict_proba(
        model_pack["preprocessor"].transform(X)
    )
    pred_idx = np.argmax(proba, axis=1) if _is_multiclass(proba) else (
        (proba[:, 1] >= (threshold if threshold is not None else 0.5)).astype(int)
    )
    score = proba.max(axis=1)

    return pd.DataFrame(
        {
            "source_row_id": df.index.astype(str),
            "predicted_label": pred_idx,
            "predicted_name": [label_map.get(str(p), str(p)) for p in pred_idx],
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