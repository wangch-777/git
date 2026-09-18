"""任务05：清理×先验×校准；prepare冻结选择，finalize一次性测试。"""
import argparse
import gc
import json
import platform
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.metrics import brier_score_loss
from sklearn.model_selection import GroupShuffleSplit

from .calibration import PlattClassifier, fit_platt, frontier, working_points, log_odds
from .cli import ROOT, write_json
from .evaluate import evaluate_binary
from .features import drop_target_and_id, load_feature_schema
from .prepare import file_sha256
from .quality import BASE, probabilities, verify
from .registry import load_model_pack
from .train import fit_model, save_model_pack_from_fit

STRATEGIES = ['drop_conflicts', 'majority', 'keep_first']
PRIORS = ['balanced', 'target_55', 'default']


def clean(frame, features, strategy):
    hashes = pd.util.hash_pandas_object(frame[features], index=False)
    grouped = frame.label.groupby(hashes)
    positives = grouped.transform('sum')
    counts = grouped.transform('size')
    conflict = (positives > 0) & (positives < counts)
    if strategy == 'drop_conflicts':
        keep = ~conflict
    elif strategy == 'majority':
        # 不重写真值；只留多数侧样本，平票组全部丢弃，避免武断裁决。
        keep = ((positives * 2 > counts) & (frame.label == 1)) | ((positives * 2 < counts) & (frame.label == 0))
    elif strategy == 'keep_first':
        keep = ~hashes.duplicated(keep='first')
    else:
        raise ValueError('未知冲突清理策略')
    return frame.loc[keep], {'removed': int((~keep).sum()), 'conflict_groups': int(hashes[conflict].nunique()),
                            'tie_groups': int(hashes[positives * 2 == counts].nunique())}


def partitions(frame, features):
    cleaned, splits, audit = {}, {}, {}
    for strategy in STRATEGIES:
        cleaned[strategy], audit[strategy] = clean(frame, features, strategy)
        hashes = pd.util.hash_pandas_object(cleaned[strategy][features], index=False)
        ti, vi = next(GroupShuffleSplit(n_splits=1, test_size=.2, random_state=42).split(cleaned[strategy], groups=hashes))
        splits[strategy] = (cleaned[strategy].iloc[ti], cleaned[strategy].iloc[vi], set(hashes.iloc[vi]))
    # 策略删掉的组不同，直接对比各自验证集会改变评价对象。
    # 在三者验证组交集上使用原始记录权重，统一选择；各自其余验证组仅拟合校准器。
    shared = set.intersection(*(item[2] for item in splits.values()))
    original_hashes = pd.util.hash_pandas_object(frame[features], index=False)
    selection = frame.loc[original_hashes.isin(shared)]
    result = {}
    for strategy, (train, val, _) in splits.items():
        val_hashes = pd.util.hash_pandas_object(val[features], index=False)
        calibration = val.loc[~val_hashes.isin(shared)]
        for part in (train, calibration, selection):
            if set(part.label.unique()) != {0, 1}:
                raise ValueError('划分缺少某个类别，不能进行公平校准与选择')
        result[strategy] = (train, calibration)
        audit[strategy].update(train_rows=len(train), validation_rows=len(val), calibration_rows=len(calibration))
    if len(selection) < 200:
        raise ValueError('共同验证组交集过小，必须重新设计协议，不能直接选参')
    return result, selection, audit


def prior_weights(labels, prior):
    if prior == 'balanced':
        return 'balanced'
    if prior == 'default':
        return None
    p = float(labels.mean())
    return {0: .45 / (1-p), 1: .55 / p}


def evaluate(labels, scores, threshold):
    result = evaluate_binary(labels, scores >= threshold, scores)
    result['fnr'] = 1 - result['recall']
    return result


def choose(results):
    return min(results, key=lambda row: (row['validation']['fnr_constraint']['fpr'],
        row['validation']['fnr_constraint']['fnr'], -row['validation']['fnr_constraint']['ap'], row['id']))


def prepare(output):
    output.mkdir(parents=True, exist_ok=False)
    source = json.loads((ROOT / 'configs/dataset_source.json').read_text(encoding='utf-8'))
    train_path = ROOT / 'data/raw/UNSW_NB15_training-set.csv'
    verify(train_path, source['files'][train_path.name]['sha256'])
    plan = {'source': source, 'seed': 42, 'max_fnr': .0323, 'cost_ratios': [1, 5, 10],
            'strategies': STRATEGIES, 'priors': PRIORS, 'rf_params': BASE,
            'target_prior': .55, 'target_prior_origin': '预设部署场景；与已知历史测试先验接近，不能视为完全盲测',
            'selection': '三策略验证组交集原始样本；其余验证组拟合Platt；在交集FNR<=0.0323下最低FPR选一次',
            'environment': {'python': platform.python_version(), 'platform': platform.platform(),
                            'sklearn': sklearn.__version__, 'numpy': np.__version__, 'pandas': pd.__version__},
            'code': {str(path.relative_to(ROOT)): file_sha256(path) for path in
                     [Path(__file__), ROOT/'ml/calibration.py', ROOT/'ml/train.py', ROOT/'ml/registry.py', ROOT/'ml/evaluate.py']}}
    write_json(output / 'plan.json', plan)
    frame = pd.read_csv(train_path)
    features = drop_target_and_id(frame).columns.tolist()
    schema = load_feature_schema(ROOT / 'configs/feature_schema.json')
    if set(features) != set(schema['numeric'] + schema['categorical']):
        raise ValueError('特征协议不一致')
    split, selection, audit = partitions(frame, features)
    indices = {'selection_indices': selection.index.tolist(), 'selection_rows': len(selection),
        'selection_label_counts': selection.label.value_counts().to_dict(), 'audit': audit,
        'strategies': {key: {'train_indices': train.index.tolist(), 'calibration_indices': cal.index.tolist()}
                       for key, (train, cal) in split.items()}}
    write_json(output / 'splits.json', indices)
    results = []
    for strategy in STRATEGIES:
        train, calibration = split[strategy]
        for prior in PRIORS:
            identifier = strategy + '-' + prior
            params = {**BASE, 'class_weight': prior_weights(train.label, prior)}
            print(f'训练 {identifier}：{len(train)}条；校准{len(calibration)}条；共同选择{len(selection)}条', flush=True)
            started = time.perf_counter()
            pipe = fit_model(train[features], train.label, 'random_forest', params, schema['numeric'], schema['categorical'])
            seconds = time.perf_counter() - started
            cal_raw = pipe.predict_proba(calibration[features])[:, list(pipe.classes_).index(1)]
            mapper = fit_platt(cal_raw, calibration.label)
            raw = pipe.predict_proba(selection[features])[:, list(pipe.classes_).index(1)]
            calibrated = mapper.predict_proba(log_odds(raw))[:, 1]
            points, curve = working_points(selection.label, calibrated, plan['max_fnr'])
            classifier = PlattClassifier(pipe.named_steps['classifier'], mapper)
            pipe.steps[-1] = ('classifier', classifier)
            directory = output / identifier
            model = Path(save_model_pack_from_fit(pipe, features, {'0': '正常', '1': '攻击'}, points['fnr_constraint'], directory,
                {'name': 'model', 'algorithm': 'random_forest', 'params': params, 'protocol': 'miss-reduction-v1',
                 'calibration': {'method': 'Platt(logit score)', 'coefficient': float(mapper.coef_[0,0]), 'intercept': float(mapper.intercept_[0])},
                 'working_points': points, 'train_rows': len(train), 'calibration_rows': len(calibration), 'selection_rows': len(selection),
                 'training_hash': source['files'][train_path.name]['sha256']}))
            item = {'id': identifier, 'strategy': strategy, 'prior': prior, 'params': params, 'thresholds': points,
                'train_seconds': seconds, 'validation': {'raw_0.5': evaluate(selection.label, raw, .5),
                    **{key: evaluate(selection.label, calibrated, t) for key,t in points.items()}},
                'brier_raw': float(brier_score_loss(selection.label, raw)), 'brier_calibrated': float(brier_score_loss(selection.label, calibrated)),
                'model': model.relative_to(output).as_posix(), 'model_hash': file_sha256(model),
                'meta_hash': file_sha256(model.with_suffix('.pack_meta.json'))}
            pd.DataFrame({'source_row_id': selection.index, 'label': selection.label, 'raw': raw, 'calibrated': calibrated}).to_csv(directory/'validation.csv', index=False)
            pd.DataFrame(curve).to_csv(directory/'validation-frontier.csv', index=False)
            results.append(item)
            write_json(output/'search.json', results)
            del pipe, classifier
            gc.collect()
    selected = choose(results)
    write_json(output/'frozen.json', {'selected': selected['id'], 'point': 'fnr_constraint', 'candidates': results,
        'plan_hash': file_sha256(output/'plan.json'), 'splits_hash': file_sha256(output/'splits.json')})
    print('仅验证选择已冻结：'+selected['id'], flush=True)


def finalize(output):
    if (output/'test-started.json').exists():
        raise ValueError('最终测试已开始过，拒绝重复评估')
    read = lambda name: json.loads((output/name).read_text(encoding='utf-8'))
    frozen, plan = read('frozen.json'), read('plan.json')
    verify(output/'plan.json', frozen['plan_hash'])
    verify(output/'splits.json', frozen['splits_hash'])
    for relative, digest in plan['code'].items():
        verify(ROOT/relative, digest)
    for item in frozen['candidates']:
        verify(output/item['model'], item['model_hash'])
        verify((output/item['model']).with_suffix('.pack_meta.json'), item['meta_hash'])
    with (output/'test-started.json').open('x', encoding='utf-8') as stream:
        json.dump({'frozen_hash': file_sha256(output/'frozen.json'), 'time': time.time()}, stream)
    for name, info in plan['source']['files'].items():
        verify(ROOT/'data/raw'/name, info['sha256'])
    train = pd.read_csv(ROOT/'data/raw/UNSW_NB15_training-set.csv')
    test = pd.read_csv(ROOT/'data/raw/UNSW_NB15_testing-set.csv')
    features = drop_target_and_id(train).columns.tolist()
    keep = ~pd.util.hash_pandas_object(test[features], index=False).isin(pd.util.hash_pandas_object(train[features], index=False))
    results = []
    for item in frozen['candidates']:
        print('一次性测试：'+item['id'], flush=True)
        pack = load_model_pack(output/item['model'])
        calibrated_classifier = pack['classifier']
        pack['classifier'] = calibrated_classifier.classifier
        raw = probabilities(pack, test)
        calibrated = calibrated_classifier.mapper.predict_proba(log_odds(raw))[:, 1]
        modes = {'raw_0.5': (raw, .5), **{key:(calibrated,t) for key,t in item['thresholds'].items()}}
        row = {'id': item['id'], 'test': {key:evaluate(test.label, scores, cutoff) for key,(scores,cutoff) in modes.items()},
               'diagnostic': {key:evaluate(test.label[keep], scores[keep], cutoff) for key,(scores,cutoff) in modes.items()}}
        # 完整测试前沿只供报告事后描述，不回传给choose，不修改冻结阈值。
        curve = frontier(test.label, calibrated)
        eligible = [p for p in curve if p['fnr'] <= plan['max_fnr'] + 1e-12]
        row['retrospective_oracle_not_recommended'] = min(eligible, key=lambda p:(p['fpr'],p['fnr']))
        pd.DataFrame(curve).to_csv(output/item['id']/'test-frontier-diagnostic.csv',index=False)
        pd.DataFrame({'label':test.label,'raw':raw,'calibrated':calibrated,'nonoverlap':keep}).to_csv(output/item['id']/'test-predictions.csv',index=False)
        results.append(row)
        del pack, calibrated_classifier
        gc.collect()
    baseline = json.loads((ROOT/'artifacts/baseline/summary.json').read_text(encoding='utf-8'))
    write_json(output/'results.json', {'selected':frozen['selected'], 'point':frozen['point'], 'rows':len(test),
        'diagnostic_rows':int(keep.sum()), 'overlap_removed':int((~keep).sum()), 'candidates':results,
        'baseline':{**baseline['metrics']['test'], 'fnr':1-baseline['metrics']['test']['recall']},
        'frozen_hash':file_sha256(output/'frozen.json')})
    print('最终结果已保存，未按测试指标重新选型。',flush=True)


if __name__ == '__main__':
    if hasattr(sys.stdout,'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description='任务05：prepare验证选择；finalize最终测试')
    parser.add_argument('phase',choices=['prepare','finalize'])
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/miss-reduction-05-v1')
    args=parser.parse_args()
    output=args.output.resolve()
    if not output.is_relative_to((ROOT/'artifacts').resolve()):
        parser.error('输出必须位于artifacts目录')
    try:
        (prepare if args.phase=='prepare' else finalize)(output)
    except (ValueError,OSError) as exc:
        parser.exit(1,f'错误：{exc}\n')
