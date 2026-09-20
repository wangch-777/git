"""特征协议与目标列处理。

监督目标列（label / attack_cat）与 id 均不得进入特征矩阵，
二分类与多分类是两个独立任务，必须显式选择检测模式。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import pandas as pd

# 这些列要么是目标、要么是标识，不能作为训练特征。
TARGET_COLUMNS = {"label", "attack_cat", "id"}


def load_feature_schema(path: str | Path) -> dict:
    """读取特征协议 JSON，返回 {numeric: [...], categorical: [...], source: str}。"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def select_feature_columns(df: pd.DataFrame, schema: dict) -> list[str]:
    """返回输入 df 中既属于 schema 又不属于目标/标识列的特征列名。"""
    declared = set(schema.get("numeric", [])) | set(schema.get("categorical", []))
    return [c for c in df.columns if c in declared and c not in TARGET_COLUMNS]


def validate_schema(df: pd.DataFrame, schema: dict) -> tuple[list[str], list[str]]:
    """校验字段。返回 (缺失列, 类型不匹配列)。"""
    numeric = schema.get("numeric", [])
    missing = [c for c in numeric if c not in df.columns]
    # 类别列不强制数字类型，交由预处理 OneHotEncoder 处理。
    return missing, []


def drop_target_and_id(df: pd.DataFrame) -> pd.DataFrame:
    """从特征矩阵中删除所有目标与标识列，防止标签泄漏。"""
    drop = [c for c in TARGET_COLUMNS if c in df.columns]
    return df.drop(columns=drop)


def _iter_selected(df: pd.DataFrame, schema: dict) -> Iterable[str]:
    return select_feature_columns(df, schema)