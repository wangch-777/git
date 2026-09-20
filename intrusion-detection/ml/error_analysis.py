"""准备只读误差诊断：验证集重新推理，测试集复用已有固定预测，不重新训练。"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

from .cli import ROOT, write_json
from .evaluate import evaluate_binary
from .features import drop_target_and_id
from .prepare import file_sha256
from .registry import load_model_pack


def threshold_metrics(truth, probability, threshold):
    truth, probability = np.asarray(truth), np.asarray(probability)
    predicted = probability >= threshold
    tn = int(((truth == 0) & ~predicted).sum())
    fp = int(((truth == 0) & predicted).sum())
    fn = int(((truth == 1) & ~predicted).sum())
    tp = int(((truth == 1) & predicted).sum())
    divide = lambda a, b: a / b if b else 0.0
    return {"threshold": threshold, "rows": len(truth), "tn": tn, "fp": fp, "fn": fn, "tp": tp,
            "accuracy": divide(tp + tn, len(truth)), "precision": divide(tp, tp + fp),
            "recall": divide(tp, tp + fn), "f1": divide(2 * tp, 2 * tp + fp + fn),
            "fpr": divide(fp, fp + tn)}


def prepare():
    base = ROOT / 'artifacts/baseline'
    model = base / 'random_forest.pack_joblib'
    meta_path = model.with_suffix('.pack_meta.json')
    meta = json.loads(meta_path.read_text(encoding='utf-8'))
    if file_sha256(model) != meta['artifact_hash']:
        raise ValueError('基础模型校验失败')
    train_path = ROOT / 'data/raw/UNSW_NB15_training-set.csv'
    test_path = ROOT / 'data/raw/UNSW_NB15_testing-set.csv'
    prediction_path = ROOT / 'data/processed/test_predictions.csv'
    for path in (train_path, test_path):
        if file_sha256(path) != meta['source']['files'][path.name]['sha256']:
            raise ValueError('源数据与基础模型不匹配')
    if meta.get('split') != 'GroupShuffleSplit on feature hashes, seed=42, validation groups=20%':
        raise ValueError('当前基础模型不符合已知验证划分协议')
    train, test = pd.read_csv(train_path), pd.read_csv(test_path)
    features = drop_target_and_id(train).columns.tolist()
    groups = pd.util.hash_pandas_object(train[features], index=False)
    ti, vi = next(GroupShuffleSplit(n_splits=1, test_size=.2, random_state=42).split(train, groups=groups))
    if len(ti) != meta['training_rows'] or len(vi) != meta['validation_rows']:
        raise ValueError('训练/验证划分与模型记录不一致')
    val = train.iloc[vi].copy()
    pack = load_model_pack(model)
    val_score = pack['classifier'].predict_proba(pack['preprocessor'].transform(val[meta['feature_list']]))[:, list(pack['classifier'].classes_).index(1)]
    # 已有预测里的score为预测类别支持度，二分类可还原攻击分数。
    predicted = pd.read_csv(prediction_path)
    if len(predicted) != len(test) or predicted.source_row_id.tolist() != list(range(len(test))):
        raise ValueError('已有测试预测行数或顺序不匹配')
    if meta['threshold'] != .5 or not predicted.predicted_label.isin([0, 1]).all() or not predicted.score.between(0, 1).all():
        raise ValueError('已有预测不符合固定0.5阈值的二分类协议')
    test_score = np.where(predicted.predicted_label == 1, predicted.score, 1 - predicted.score)
    summary = json.loads((base / 'summary.json').read_text(encoding='utf-8'))
    for split, frame, scores in [('validation', val, val_score), ('test', test, test_score)]:
        actual = evaluate_binary(frame.label, scores >= .5, scores)
        # 由1-score还原的测试分数存在浮点舍入，AP并列排序可能微变；
        # 页面测试AP沿用原报告，此处仅核验固定阈值的五项分类指标。
        keys = actual.keys() if split == 'validation' else ('precision', 'recall', 'f1', 'fpr', 'accuracy')
        if any(not np.isclose(actual[key], summary['metrics'][split][key], rtol=0, atol=1e-10) for key in keys):
            raise ValueError('诊断预测与既有基础模型指标不一致')
    out = base / 'diagnostics'
    out.mkdir(exist_ok=True)
    manifest = {'version': 1, 'fixed_threshold': .5, 'model_hash': file_sha256(model),
                'sources': {str(path.relative_to(ROOT)): file_sha256(path) for path in
                    (model, meta_path, train_path, test_path, prediction_path, base / 'summary.json')},
                'files': {}, 'thresholds': [threshold_metrics(val.label, val_score, i / 100) for i in range(101)],
                'test': threshold_metrics(test.label, test_score, .5)}
    for split, frame, scores in [('validation', val, val_score), ('test', test, test_score)]:
        frame = frame.copy()
        frame.insert(0, 'source_row_id', frame.index)
        frame['attack_score'] = scores
        path = out / f'{split}.csv'
        temp = path.with_suffix('.tmp')
        frame.to_csv(temp, index=False, encoding='utf-8-sig')
        temp.replace(path)
        manifest['files'][split] = file_sha256(path)
    write_json(out / 'manifest.tmp', manifest)
    (out / 'manifest.tmp').replace(out / 'manifest.json')
    print('误差诊断已准备；验证阈值网格0至1，测试阈值固定0.5。')


if __name__ == '__main__':
    prepare()
