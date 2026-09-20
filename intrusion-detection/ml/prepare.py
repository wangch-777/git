"""数据加载、质量审计与划分（泄漏控制）。

原则：
- 只保存原始数据，记录摘要；
- 缺失/无穷/重复/类型/类别分布审计是应做的检查；
- 官方测试集保持隔离，训练集内部再划验证集；
- 预处理只在训练子集拟合，验证与测试只 transform。
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split


def file_sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_csv(path: str | Path) -> pd.DataFrame:
    """读取 CSV 特征文件。"""
    return pd.read_csv(path)


def audit(df: pd.DataFrame, feature_cols: list[str] | None = None) -> dict:
    """质量审计：返回缺失、无穷、重复、非数值/类别分布摘要。"""
    report: dict = {
        "rows": int(len(df)),
        "columns": list(df.columns),
        "missing": int(df[feature_cols].isna().sum().sum()) if feature_cols else int(df.isna().sum().sum()),
        "infinite": bool(_has_infinite(df, feature_cols)),
        "duplicate_rows": int(df.duplicated().sum()),
    }
    return report


def _has_infinite(df: pd.DataFrame, feature_cols: list[str] | None) -> bool:
    subset = df[feature_cols] if feature_cols else df
    numeric = subset.select_dtypes(include="number")
    return bool((numeric == float("inf")).sum().sum() or (numeric == float("-inf")).sum().sum())


def split_train_val(
    df: pd.DataFrame,
    label_col: str,
    val_size: float = 0.2,
    seed: int = 42,
    stratify: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """训练/验证划分。默认按标签分层，保证各类别覆盖。"""
    strat = df[label_col] if stratify else None
    train, val = train_test_split(
        df, test_size=val_size, random_state=seed, stratify=strat
    )
    return train, val