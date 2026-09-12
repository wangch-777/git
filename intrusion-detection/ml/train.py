"""模型训练：构建预处理管道 + 分类器 + 保存可追溯模型包。

模型包（Model Pack）包含预处理器、分类器、特征清单、标签映射、
阈值、数据版本、依赖版本与训练参数，推理端复用完整模型包。
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier

from .registry import save_model_pack

SUPPORTED_ALGORITHMS = {
    "dummy": DummyClassifier,
    "logistic_regression": LogisticRegression,
    "decision_tree": DecisionTreeClassifier,
    "random_forest": RandomForestClassifier,
}


def build_estimator(algorithm: str, params: dict | None = None):
    """根据算法名构建分类器。"""
    if algorithm not in SUPPORTED_ALGORITHMS:
        raise ValueError(f"未知算法: {algorithm}")
    cls = SUPPORTED_ALGORITHMS[algorithm]
    return cls(**(params or {}))


def build_preprocessor(
    numeric_cols: list[str], categorical_cols: list[str]
) -> ColumnTransformer:
    """数值列填补+标准化；类别列 OneHot 且 handle_unknown='ignore'。"""
    numeric_pipe = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    categorical_pipe = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore")),
        ]
    )
    return ColumnTransformer(
        transformers=[
            ("num", numeric_pipe, numeric_cols),
            ("cat", categorical_pipe, categorical_cols),
        ]
    )


def fit_model(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    algorithm: str,
    params: dict | None = None,
    numeric_cols: list[str] | None = None,
    categorical_cols: list[str] | None = None,
) -> Pipeline:
    """拟合完整 Pipeline（预处理 + 分类器）。"""
    numeric_cols = numeric_cols or X_train.select_dtypes(include="number").columns.tolist()
    categorical_cols = categorical_cols or X_train.select_dtypes(exclude="number").columns.tolist()

    pipeline = Pipeline(
        steps=[
            ("preprocess", build_preprocessor(numeric_cols, categorical_cols)),
            ("classifier", build_estimator(algorithm, params)),
        ]
    )
    pipeline.fit(X_train, y_train)
    return pipeline


def save_model_pack_from_fit(
    pipeline: Pipeline,
    feature_list: list[str],
    label_map: dict,
    threshold: float | None,
    out_dir: str | Path,
    metadata: dict | None = None,
) -> str:
    """抽取预处理器与分类器并保存为模型包。"""
    return save_model_pack(
        out_dir=out_dir,
        preprocessor=pipeline.named_steps["preprocess"],
        classifier=pipeline.named_steps["classifier"],
        feature_list=feature_list,
        label_map=label_map,
        threshold=threshold,
        metadata=metadata or {},
    )