import json

import numpy as np
import pandas as pd
import pytest

from backend.app.config import settings
from ml.cli import write_json
from ml.error_analysis import threshold_metrics
from ml.prepare import file_sha256
from tests.test_detection_flow import flow


def fixture_data():
    directory = settings.artifacts / 'baseline/diagnostics'
    directory.mkdir()
    frame = pd.DataFrame({'source_row_id': [2, 5, 8, 12], 'id': [3, 6, 9, 13],
                          'label': [0, 0, 1, 1], 'attack_score': [.2, .7, .3, .9],
                          'proto': ['tcp']*4, 'attack_cat': ['Normal', 'Normal', 'Generic', 'Generic']})
    files = {}
    for scope in ('validation', 'test'):
        path = directory / f'{scope}.csv'
        frame.to_csv(path, index=False)
        files[scope] = file_sha256(path)
    manifest = {'model_hash': 'test', 'sources': {}, 'fixed_threshold': .5, 'files': files,
        'thresholds': [threshold_metrics(frame.label, frame.attack_score, i/100) for i in range(101)],
        'test': threshold_metrics(frame.label, frame.attack_score, .5)}
    write_json(directory / 'manifest.json', manifest)
    return directory


def test_threshold_extremes_and_equal_score():
    truth, score = [0, 0, 1, 1], [.2, .7, .3, .9]
    assert threshold_metrics(truth, score, 0)['fp'] == 2
    assert threshold_metrics(truth, score, 1)['fn'] == 2
    # >=规则：0.7恰好等于阈值，仍归为攻击。
    assert threshold_metrics(truth, score, .7)['fp'] == 1
    assert threshold_metrics(truth, score, .71)['fp'] == 0


def test_error_samples_follow_scope_threshold_and_pagination(flow):
    client, _ = flow
    directory = fixture_data()
    overview = client.get('/api/evaluation/diagnostics').json()
    assert overview['thresholds'][50]['fp'] == 1
    fp = client.get('/api/evaluation/errors?kind=fp').json()
    fn = client.get('/api/evaluation/errors?kind=fn').json()
    assert fp['items'][0]['source_row_id'] == 5
    assert fp['items'][0]['true_name'] == '正常'
    assert fn['items'][0]['source_row_id'] == 8
    assert fn['items'][0]['true_name'] == '攻击'
    assert client.get('/api/evaluation/errors?threshold=0.71').json()['total'] == 0
    assert client.get('/api/evaluation/errors?page=2&page_size=1').json()['items'] == []
    assert client.get('/api/evaluation/errors?split=test&threshold=0.71').status_code == 422
    assert client.get('/api/evaluation/errors?threshold=0.555').status_code == 422
    assert client.get('/api/evaluation/errors?kind=unknown').status_code == 422
    (directory / 'validation.csv').write_text('changed')
    assert client.get('/api/evaluation/errors').status_code == 409


def test_analysis_missing_and_stale_sources(flow):
    client, _ = flow
    assert client.get('/api/evaluation/diagnostics').status_code == 404
    assert client.get('/api/evaluation/duplicates').status_code == 404
    directory = fixture_data()
    manifest = json.loads((directory / 'manifest.json').read_text())
    manifest['sources'] = {'missing-source.csv': 'wrong'}
    write_json(directory / 'manifest.json', manifest)
    assert client.get('/api/evaluation/diagnostics').status_code == 409
