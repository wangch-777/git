import pandas as pd
import pytest

from ml.cli import predict_csv
from ml.train import fit_model, save_model_pack_from_fit


@pytest.fixture
def model(tmp_path):
    pipe = fit_model(pd.DataFrame({"dur": [1., 2., 3., 4.]}), pd.Series([0, 0, 0, 1]),
                     "dummy", {"strategy": "prior"})
    return save_model_pack_from_fit(pipe, ["dur"], {"0": "正常", "1": "攻击"}, .5, tmp_path)


def test_csv_prediction_across_chunk_boundary(model, tmp_path):
    input_path, output = tmp_path / "input.csv", tmp_path / "result.csv"
    pd.DataFrame({"dur": [1.] * 10001}).to_csv(input_path, index=False)
    assert predict_csv(model, input_path, output) == 10001
    result = pd.read_csv(output)
    assert result.source_row_id.tolist() == list(range(10001))
    assert result.predicted_name.unique().tolist() == ["正常"]
    assert output.read_bytes().startswith(b"\xef\xbb\xbf")


@pytest.mark.parametrize("content", ["dur\n", "dur,dur\n1,2\n", "other\n1\n"])
def test_bad_csv_does_not_replace_existing_output(model, tmp_path, content):
    input_path, output = tmp_path / "input.csv", tmp_path / "result.csv"
    input_path.write_text(content)
    output.write_text("previous valid result")
    with pytest.raises(ValueError):
        predict_csv(model, input_path, output)
    assert output.read_text() == "previous valid result"
