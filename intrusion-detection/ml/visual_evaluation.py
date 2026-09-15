"""Evaluation charts from labelled data and actual attack probabilities."""
import numpy as np
from sklearn.metrics import confusion_matrix, precision_recall_curve, precision_recall_fscore_support
from .evaluate import evaluate_binary


def chart_metrics(truth, predictions, probabilities):
    precision, recall, _ = precision_recall_curve(truth, probabilities)
    indices = np.unique(np.linspace(0, len(precision) - 1, min(250, len(precision)), dtype=int))
    p, r, f, support = precision_recall_fscore_support(truth, predictions, labels=[0, 1], zero_division=0)
    return {
        "metrics": evaluate_binary(truth, predictions, probabilities),
        "confusion": confusion_matrix(truth, predictions, labels=[0, 1]).tolist(),
        "classes": [{"name": name, "precision": float(p[i]), "recall": float(r[i]),
                     "f1": float(f[i]), "support": int(support[i])}
                    for i, name in enumerate(["正常", "攻击"])],
        "pr_curve": [[float(recall[i]), float(precision[i])] for i in indices],
    }
