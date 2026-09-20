import io
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine, inspect, text

from backend.app.database import initialize_database
from backend.app.db_models import DetectionTask
from backend.app.services import detection
from tests.test_detection_flow import flow, create_task
from worker import worker


def completed(client, sessions, count=23017, cached=True):
    task_id = create_task(client)
    frame = pd.DataFrame({'source_row_id': range(count), 'predicted_label': [i % 3 == 0 for i in range(count)]})
    frame.predicted_label = frame.predicted_label.astype(int)
    frame['predicted_name'] = frame.predicted_label.map({0: '正常', 1: '攻击'})
    frame['score'] = .875
    with sessions() as db:
        task = db.get(DetectionTask, task_id)
        path = Path(detection.settings.data_processed) / 'test-results.csv'
        frame.to_csv(path, index=False, encoding='utf-8-sig')
        task.status, task.result_path, task.total_rows, task.processed_rows = 'succeeded', str(path), count, count
        if cached:
            task.attack_count = int(frame.predicted_label.sum())
            task.normal_count = count - task.attack_count
        db.commit()
    return task_id, frame, path


@pytest.mark.parametrize('cached', [False, True])
def test_statistics_cache_and_legacy_backfill(flow, monkeypatch, cached):
    client, sessions = flow
    task_id, frame, _ = completed(client, sessions, cached=cached)
    original = pd.read_csv
    calls = []
    def bounded(*args, **kwargs):
        assert kwargs.get('chunksize') == 10000
        calls.append(kwargs)
        return original(*args, **kwargs)
    monkeypatch.setattr(pd, 'read_csv', bounded)
    for label in (None, 0, 1):
        expected = frame if label is None else frame.loc[frame.predicted_label == label]
        response = client.get(f'/api/detections/{task_id}/statistics', params={} if label is None else {'label': label})
        assert response.json() == detection.statistics(len(expected) - int(expected.predicted_label.sum()), int(expected.predicted_label.sum()))
    assert len(calls) == (0 if cached else 1)
    with sessions() as db:
        task = db.get(DetectionTask, task_id)
        assert task.normal_count + task.attack_count == len(frame)


@pytest.mark.parametrize('label', [None, 0, 1])
def test_page_boundaries_and_export(flow, monkeypatch, label):
    client, sessions = flow
    task_id, frame, _ = completed(client, sessions)
    expected = frame if label is None else frame.loc[frame.predicted_label == label]
    params = {} if label is None else {'label': label}
    original = pd.read_csv
    def bounded(*args, **kwargs):
        assert kwargs.get('chunksize') or kwargs.get('nrows')
        if kwargs.get('skiprows'):
            assert callable(kwargs['skiprows'])
        return original(*args, **kwargs)
    monkeypatch.setattr(pd, 'read_csv', bounded)
    for page in (1, 500, (len(expected) + 19) // 20, 100000000):
        response = client.get(f'/api/detections/{task_id}/results', params={**params, 'page': page})
        assert response.json() == {'total': len(expected), 'items': expected.iloc[(page - 1)*20:page*20].to_dict('records')}
    response = client.get(f'/api/detections/{task_id}/report', params=params)
    assert response.content.count(b'\xef\xbb\xbf') == 1
    assert response.content.count(b'source_row_id,') == 1
    assert f'detection-{task_id}-' in response.headers['content-disposition']
    pd.testing.assert_frame_equal(original(io.BytesIO(response.content)), expected.reset_index(drop=True))


def test_worker_persists_counts_and_zero_match_export(flow):
    client, sessions = flow
    task_id = create_task(client)
    worker.run_once()
    with sessions() as db:
        task = db.get(DetectionTask, task_id)
        assert (task.normal_count, task.attack_count) == (2, 2)
    task_id, _, path = completed(client, sessions, count=1)
    response = client.get(f'/api/detections/{task_id}/report?label=0')
    frame = pd.read_csv(io.BytesIO(response.content))
    assert frame.empty and list(frame.columns) == ['source_row_id', 'predicted_label', 'predicted_name', 'score']
    path.unlink()
    assert client.get(f'/api/detections/{task_id}/results').status_code == 410
    assert client.get(f'/api/detections/{task_id}/report').status_code == 410
    # 已保存的摘要独立于CSV，文件缺失仍能返回历史统计。
    assert client.get(f'/api/detections/{task_id}/statistics').json()['total'] == 1


def test_detection_migration_nullable_and_idempotent(tmp_path):
    path = tmp_path / 'legacy.db'
    engine = create_engine(f'sqlite:///{path}')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE detection_tasks (id INTEGER PRIMARY KEY, status TEXT)'))
        conn.execute(text("INSERT INTO detection_tasks VALUES (7, 'succeeded')"))
    initialize_database(engine)
    initialize_database(engine)
    with engine.connect() as conn:
        assert conn.execute(text('SELECT id,normal_count,attack_count FROM detection_tasks')).one() == (7, None, None)
    backup = tmp_path / 'legacy-before-detection-counts.sqlite3'
    old = create_engine(f'sqlite:///{backup}')
    assert 'normal_count' not in {c['name'] for c in inspect(old).get_columns('detection_tasks')}
    old.dispose()
    engine.dispose()


def test_export_yields_before_reading_entire_file_and_closes(flow):
    client, sessions = flow
    _, _, path = completed(client, sessions)
    stream = detection.stream_result(path)
    first = next(stream)
    assert len(first) == 65536 and path.stat().st_size > len(first)
    stream.close()
    # Windows下未关闭文件句柄会阻止删除。
    path.unlink()
