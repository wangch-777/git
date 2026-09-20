"""评价指标测试。"""
import numpy as np

from ml.evaluate import evaluate_binary, evaluate_multiclass


def test_evaluate_binary_known_values():
    y_true = [0, 0, 1, 1]
    y_pred = [0, 1, 0, 1]
    r = evaluate_binary(y_true, y_pred, y_score=None)
    assert abs(r["precision"] - 0.5) < 1e-9
    assert abs(r["recall"] - 0.5) < 1e-9
    assert abs(r["f1"] - 0.5) < 1e-9
    assert abs(r["fpr"] - 0.5) < 1e-9
    assert abs(r["accuracy"] - 0.5) < 1e-9
    assert r["ap"] is None


def test_evaluate_multiclass_returns_per_class():
    y_true = [0, 1, 2, 2]
    y_pred = [0, 1, 1, 2]
    r = evaluate_multiclass(y_true, y_pred)
    assert "macro_f1" in r
    assert "weighted_f1" in r
    assert set(r["per_class"].keys()) == {"0", "1", "2"}