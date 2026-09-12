"""端到端冒烟测试：train -> save -> load -> predict 全链路。"""
import tempfile

import numpy as np
import pandas as pd

from ml.predict import predict_dataframe
from ml.registry import load_model_pack
from ml.train import fit_model, save_model_pack_from_fit


def _synthetic_df(n: int = 200) -> pd.DataFrame:
    rng = np.random.RandomState(0)
    return pd.DataFrame(
        {
            "id": range(n),
            "dur": rng.rand(n),
            "sbytes": rng.randint(0, 1000, n).astype(float),
            "proto": rng.choice(["tcp", "udp", "icmp"], n),
            "label": rng.choice([0, 1], n),
        }
    )


def test_train_save_load_predict_roundtrip():
    df = _synthetic_df()
    feature_list = ["dur", "sbytes", "proto"]
    X = df[feature_list]
    y = df["label"]

    pipeline = fit_model(
        X, y, algorithm="logistic_regression", params={"max_iter": 1000}
    )

    with tempfile.TemporaryDirectory() as d:
        path = save_model_pack_from_fit(
            pipeline,
            feature_list=feature_list,
            label_map={"0": "normal", "1": "attack"},
            threshold=0.5,
            out_dir=d,
            metadata={"name": "smoke"},
        )
        pack = load_model_pack(path)
        out = predict_dataframe(pack, df)

    assert out["predicted_label"].isin({0, 1}).all()
    assert list(out.columns) == [
        "source_row_id",
        "predicted_label",
        "predicted_name",
        "score",
    ]
    assert len(out) == len(df)