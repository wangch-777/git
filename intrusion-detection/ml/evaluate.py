"""评价指标：二分类与多分类。

口径：二分类以"攻击"为正类；报告 Precision/Recall/F1/FPR/AP，
Accuracy 仅作补充。多分类报告 Macro-F1、Weighted-F1、每类 Recall/F1/support。
"""
from __future__ import annotations

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
    precision_score,
    recall_score,
)


def evaluate_binary(y_true, y_pred, y_score=None) -> dict:
    """二分类指标。y_score 用于 Average Precision。"""
    result = {
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "fpr": _fpr(y_true, y_pred),
        "accuracy": float(np.mean(np.asarray(y_true) == np.asarray(y_pred))),
        "ap": float(average_precision_score(y_true, y_score)) if y_score is not None else None,
    }
    return result


def evaluate_multiclass(y_true, y_pred) -> dict:
    """多分类指标，返回各类别明细与宏/加权汇总。"""
    macro_f1 = float(f1_score(y_true, y_pred, average="macro", zero_division=0))
    weighted_f1 = float(f1_score(y_true, y_pred, average="weighted", zero_division=0))
    p, r, f1, support = precision_recall_fscore_support(
        y_true, y_pred, zero_division=0
    )
    return {
        "macro_f1": macro_f1,
        "weighted_f1": weighted_f1,
        "per_class": {
            str(cls): {
                "precision": float(p[i]),
                "recall": float(r[i]),
                "f1": float(f1[i]),
                "support": int(support[i]),
            }
            for i, cls in enumerate(np.unique(np.concatenate([np.asarray(y_true), np.asarray(y_pred)])))
        },
    }


def _fpr(y_true, y_pred) -> float:
    """FPR = FP / (FP + TN)，与 1 - Precision 不同。"""
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    return float(fp / (fp + tn)) if (fp + tn) > 0 else 0.0