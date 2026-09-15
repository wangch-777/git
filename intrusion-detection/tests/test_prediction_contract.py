import pandas as pd
import pytest

from ml.predict import predict_dataframe
from ml.train import fit_model


@pytest.fixture
def pack():
    pipe = fit_model(pd.DataFrame({"dur": [1., 2., 3., 4.]}),
                     pd.Series([0, 0, 0, 1]), "dummy", {"strategy": "prior"})
    return {"preprocessor": pipe.named_steps["preprocess"],
            "classifier": pipe.named_steps["classifier"],
            "meta": {"feature_list": ["dur"], "label_map": {"0": "正常", "1": "攻击"},
                     "threshold": 0.2}}


def test_missing_feature_rejected_instead_of_silent_imputation(pack):
    with pytest.raises(ValueError, match="dur"):
        predict_dataframe(pack, pd.DataFrame({"other": [1]}))


def test_threshold_score_belongs_to_selected_class(pack):
    out = predict_dataframe(pack, pd.DataFrame({"dur": [1.]}))
    assert out.predicted_name.iloc[0] == "攻击"
    assert out.score.iloc[0] == pytest.approx(0.25)


def test_non_contiguous_classes_are_not_probability_indices(pack):
    pack["classifier"].classes_ = [2, 7]
    pack["meta"]["label_map"] = {"2": "two", "7": "seven"}
    import numpy as np
    pack["classifier"].classes_ = np.array([2, 7])
    out = predict_dataframe(pack, pd.DataFrame({"dur": [1.]}))
    assert out.predicted_label.iloc[0] == 2
    assert out.predicted_name.iloc[0] == "two"


def test_column_order_and_labels_do_not_change_prediction(pack):
    plain = pd.DataFrame({"dur": [1., 2.]})
    extra = plain.assign(label=1, attack_cat="DoS", id=9)[["id", "label", "dur", "attack_cat"]]
    pd.testing.assert_frame_equal(predict_dataframe(pack, plain), predict_dataframe(pack, extra))


def test_invalid_number_rejected(pack):
    with pytest.raises(ValueError, match="数值"):
        predict_dataframe(pack, pd.DataFrame({"dur": ["invalid"]}))
