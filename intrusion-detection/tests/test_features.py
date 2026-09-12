"""特征协议与泄漏控制测试。"""
import pandas as pd

from ml.features import drop_target_and_id, select_feature_columns

SCHEMA = {
    "numeric": ["dur", "sbytes", "dbytes"],
    "categorical": ["proto", "service"],
}


def _df():
    return pd.DataFrame(
        {
            "id": [1, 2],
            "dur": [0.1, 0.2],
            "sbytes": [10, 20],
            "dbytes": [30, 40],
            "proto": ["tcp", "udp"],
            "service": ["-", "dns"],
            "label": [0, 1],
            "attack_cat": ["Normal", "DoS"],
        }
    )


def test_select_feature_columns_excludes_target_and_id():
    cols = select_feature_columns(_df(), SCHEMA)
    assert "label" not in cols
    assert "attack_cat" not in cols
    assert "id" not in cols
    assert cols == ["dur", "sbytes", "dbytes", "proto", "service"]


def test_drop_target_and_id():
    out = drop_target_and_id(_df())
    assert "label" not in out.columns
    assert "attack_cat" not in out.columns
    assert "id" not in out.columns