import numpy as np
import pandas as pd
import pytest

from ml.quality import split_training, select_threshold, undersample, choose_candidate, finalize
from ml.evaluate import evaluate_binary


def test_dedup_keeps_first_label_and_groups_do_not_leak():
    frame = pd.DataFrame({"x": list(range(40)) + [0, 1], "label": [0, 1] * 20 + [1, 0]})
    train, val, _ = split_training(frame, ["x"])
    combined = pd.concat([train, val])
    assert len(combined) == 40
    assert combined.loc[0, "label"] == 0
    assert combined.loc[1, "label"] == 1
    assert set(train.x).isdisjoint(val.x)
    again, _, _ = split_training(frame, ["x"])
    assert train.index.equals(again.index)


def test_threshold_matches_exhaustive_search_with_tied_scores():
    y = np.array([0, 0, 0, 1, 1, 1, 1, 1])
    scores = np.array([.1, .4, .7, .4, .5, .6, .7, .9])
    cutoff, curve = select_threshold(y, scores, .8)
    candidates = []
    for t in np.unique(scores):
        m = evaluate_binary(y, scores >= t, scores)
        if m['recall'] >= .8:
            candidates.append((m['fpr'], -m['recall'], -t))
    assert cutoff == -min(candidates)[2]
    assert curve.threshold.is_monotonic_decreasing


def test_under_sampling_affects_only_fit_rows_and_balances():
    frame = pd.DataFrame({"label": [0] * 5 + [1] * 15})
    before = frame.copy(deep=True)
    result = undersample(frame)
    assert result.label.value_counts().to_dict() == {0: 5, 1: 5}
    pd.testing.assert_frame_equal(frame, before)
    pd.testing.assert_frame_equal(result, undersample(frame))


def test_selection_never_uses_test_metrics():
    candidates = [{"id": "a", "validation": {"f1": .8, "ap": .9}, "test": {"f1": 1}},
                  {"id": "b", "validation": {"f1": .9, "ap": .8}, "test": {"f1": 0}}]
    assert choose_candidate(candidates)['id'] == 'b'
    candidates[0]['test']['f1'], candidates[1]['test']['f1'] = 0, 1
    assert choose_candidate(candidates)['id'] == 'b'


def test_finalize_refuses_second_attempt_before_reading_data(tmp_path):
    (tmp_path / 'test-started.json').write_text('{}')
    with pytest.raises(ValueError, match="拒绝重复"):
        finalize(tmp_path)


def test_invalid_threshold_input():
    with pytest.raises(ValueError):
        select_threshold(np.array([0, 0]), np.array([.2, .5]))


def test_prepare_needs_no_test_file_and_finalize_rejects_changed_model(tmp_path, monkeypatch):
    import json
    import ml.quality as quality
    from ml.registry import load_model_pack
    from ml.prepare import file_sha256

    raw = tmp_path / 'data/raw'
    raw.mkdir(parents=True)
    config = tmp_path / 'configs'
    config.mkdir()
    frame = pd.DataFrame({'id': range(100), 'x': range(100),
                          'category': ['tcp', 'udp'] * 50, 'label': [0, 1] * 50})
    source = raw / 'UNSW_NB15_training-set.csv'
    frame.to_csv(source, index=False)
    (config / 'dataset_source.json').write_text(json.dumps({'files': {
        source.name: {'sha256': file_sha256(source)}}}))
    (config / 'feature_schema.json').write_text(json.dumps({'numeric': ['x'], 'categorical': ['category']}))
    monkeypatch.setattr(quality, 'ROOT', tmp_path)
    monkeypatch.setattr(quality, 'CANDIDATES', [{'id': 'B', 'params': {
        **quality.BASE, 'n_estimators': 5}, 'undersample': False}])
    output = tmp_path / 'artifacts/test'
    quality.prepare(output)
    frozen = json.loads((output / 'frozen.json').read_text())
    split = json.loads((output / 'split.json').read_text())
    model = output / frozen['candidates'][0]['model']
    pack = load_model_pack(model)
    scaler = pack['preprocessor'].named_transformers_['num'].named_steps['scaler']
    assert scaler.mean_[0] == frame.iloc[split['train_indices']].x.mean()
    assert not (raw / 'UNSW_NB15_testing-set.csv').exists()
    model.write_bytes(b'changed')
    with pytest.raises(ValueError, match='摘要发生变化'):
        quality.finalize(output)
    assert not (output / 'test-started.json').exists()
