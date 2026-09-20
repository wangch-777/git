"""可序列化的二分类Platt校准器，复用现有模型包和Worker预测协议。"""
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.metrics import roc_curve


def log_odds(probabilities):
    p = np.clip(np.asarray(probabilities, dtype=float), 1e-8, 1 - 1e-8)
    return np.log(p / (1 - p)).reshape(-1, 1)


def fit_platt(probabilities, labels):
    if set(np.unique(labels)) != {0, 1}:
        raise ValueError('校准集必须包含正常和攻击两类')
    mapper = LogisticRegression(C=1e6, max_iter=1000, random_state=42)
    mapper.fit(log_odds(probabilities), labels)
    if mapper.coef_[0, 0] <= 0:
        raise ValueError('校准映射非单调递增，不能沿用原攻击分数排序')
    return mapper


class PlattClassifier(ClassifierMixin, BaseEstimator):
    def __init__(self, classifier, mapper):
        self.classifier = classifier
        self.mapper = mapper
        self.classes_ = np.asarray(classifier.classes_)
        if set(self.classes_) != {0, 1}:
            raise ValueError('校准仅支持正常0/攻击1')

    def fit(self, features, labels=None):
        raise ValueError('此包装器仅封装已拟合模型；请分别训练分类器并用独立数据校准')

    def __sklearn_is_fitted__(self):
        return True

    def predict_proba(self, features):
        positive = list(self.classes_).index(1)
        raw = self.classifier.predict_proba(features)[:, positive]
        calibrated = self.mapper.predict_proba(log_odds(raw))[:, list(self.mapper.classes_).index(1)]
        return np.column_stack([calibrated if label == 1 else 1 - calibrated for label in self.classes_])


def frontier(labels, scores):
    fpr, recall, cutoffs = roc_curve(labels, scores, drop_intermediate=False)
    # 全判正常端点使用略大于最大分数的有限阈值，可被现有0..1协议接受。
    if cutoffs[0] > 1:
        cutoffs[0] = min(1.0, float(np.nextafter(np.max(scores), np.inf)))
        if np.max(scores) == 1:
            fpr, recall, cutoffs = fpr[1:], recall[1:], cutoffs[1:]
    return [{'threshold': float(t), 'fpr': float(f), 'fnr': float(1-r), 'recall': float(r)}
            for f, r, t in zip(fpr, recall, cutoffs)]


def working_points(labels, scores, max_fnr=.0323):
    curve = frontier(labels, scores)
    p = float(np.mean(np.asarray(labels) == 1))
    result = {'calibrated_0.5': .5}
    for cost in (1, 5, 10):
        chosen = min(curve, key=lambda row: (cost * p * row['fnr'] + (1-p) * row['fpr'], row['fnr'], row['fpr']))
        result[f'cost_{cost}'] = chosen['threshold']
    eligible = [row for row in curve if row['fnr'] <= max_fnr + 1e-12]
    result['fnr_constraint'] = min(eligible, key=lambda row: (row['fpr'], row['fnr'], -row['threshold']))['threshold']
    return result, curve
