"""基础模型误差样本与验证阈值实验；不修改模型，不提供测试集调阈值。"""
import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from ml.prepare import file_sha256
from ..config import settings

router = APIRouter()


@lru_cache(maxsize=32)
def cached_hash(path, modified, size):
    return file_sha256(Path(path))


def verify(path, digest):
    try:
        stat = path.stat()
        valid = cached_hash(str(path), stat.st_mtime_ns, stat.st_size) == digest
    except OSError:
        valid = False
    if not valid:
        raise HTTPException(409, '诊断数据或模型已变化，请重新生成误差诊断数据')


def manifest():
    directory = settings.artifacts / 'baseline/diagnostics'
    path = directory / 'manifest.json'
    if not path.exists():
        raise HTTPException(404, '尚未准备误差诊断，请运行 python -m ml.error_analysis')
    data = json.loads(path.read_text(encoding='utf-8'))
    for relative, digest in data['sources'].items():
        verify(settings.project_root / relative, digest)
    return directory, data


@router.get('/diagnostics')
def overview():
    _, data = manifest()
    return {key: data[key] for key in ('model_hash', 'fixed_threshold', 'thresholds', 'test')}


@router.get('/errors')
def errors(split: Literal['validation', 'test'] = 'validation',
           kind: Literal['fp', 'fn'] = 'fp', threshold: float = Query(.5, ge=0, le=1),
           page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    directory, data = manifest()
    if split == 'test' and threshold != data['fixed_threshold']:
        raise HTTPException(422, '测试集仅展示固定阈值结果，调整阈值请使用验证集')
    index = round(threshold * 100)
    if abs(index / 100 - threshold) > 1e-9:
        raise HTTPException(422, '阈值步长为0.01')
    summary = data['test'] if split == 'test' else data['thresholds'][index]
    total = summary[kind]
    path = directory / f'{split}.csv'
    verify(path, data['files'][split])
    start, matched, items = (page - 1) * page_size, 0, []
    if start < total:
        with pd.read_csv(path, chunksize=5000) as chunks:
            for chunk in chunks:
                positive = chunk.attack_score >= threshold
                selected = chunk.loc[((chunk.label == 0) & positive) if kind == 'fp' else ((chunk.label == 1) & ~positive)]
                offset = max(0, start - matched)
                if offset < len(selected):
                    for record in selected.iloc[offset:offset + page_size - len(items)].to_dict('records'):
                        record['true_name'] = '正常' if record['label'] == 0 else '攻击'
                        record['predicted_name'] = '攻击' if kind == 'fp' else '正常'
                        # DataFrame逐列推断可能含NaN，用JSON空值展示。
                        items.append({key: None if pd.isna(value) else value for key, value in record.items()})
                matched += len(selected)
                if len(items) == page_size:
                    break
    return {'total': total, 'items': items, 'split': split, 'threshold': threshold,
            'source_file': 'UNSW_NB15_training-set.csv' if split == 'validation' else 'UNSW_NB15_testing-set.csv'}


@router.get('/duplicates')
def duplicates():
    directory = settings.artifacts / 'quality-02'
    if not (directory / 'results.json').exists():
        raise HTTPException(404, '尚无已完成的去重实验，请先完成质量实验并生成报告')
    read = lambda name: json.loads((directory / name).read_text(encoding='utf-8'))
    result, frozen, split, plan = (read(name) for name in ('results.json', 'frozen.json', 'split.json', 'plan.json'))
    verify(directory / 'frozen.json', result['frozen_hash'])
    verify(directory / 'split.json', frozen['split_hash'])
    verify(directory / 'plan.json', frozen['plan_hash'])
    rows = []
    for label, name, training, removed in [('A', '未去重基线', result['metrics']['A']['train_rows'], 0),
                                           ('B', '训练源去重', split['train_rows'], split['removed_rows'])]:
        for scope in ('validation', 'test'):
            rows.append({'name': name, 'scope': '验证集' if scope == 'validation' else '原测试集',
                'train_rows': training, 'removed': removed, 'diagnostic': False,
                **result['metrics'][label][scope]})
    for key, name in [('C_A', '未去重模型·非重叠测试子集'), ('C_B', '去重模型·非重叠测试子集')]:
        rows.append({'name': name, 'scope': '仅诊断', 'diagnostic': True, 'rows': result['diagnostic_rows'], **result['metrics'][key]})
    a, b = result['metrics']['A']['test']['fpr'], result['metrics']['B']['test']['fpr']
    delta = (b - a) * 100
    conclusion = f'固定0.5阈值下，训练源去重后测试误报率从{a:.2%}变为{b:.2%}，变化{delta:+.2f}个百分点。'
    conclusion += '本次去重没有改善误报，不建议直接替换现有基线。' if delta >= 0 else '本次误报有所下降，仍需结合召回率和F1判断。'
    return {'rows': rows, 'removed': split['removed_rows'], 'conflicts': split['conflicting_label_groups'],
            'overlap': result['overlap_removed'], 'conclusion': conclusion,
            'limitations': '验证集条数和重复权重随去重改变，验证指标不能直接作因果比较；非重叠测试子集仅供诊断，不是最终成绩或泛化上界。',
            'source': '任务02已冻结实验，种子42，非当前滑块阈值',
            'selected': result['metrics']['selected']}
