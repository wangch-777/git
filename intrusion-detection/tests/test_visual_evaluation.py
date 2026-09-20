import pytest
from ml.visual_evaluation import chart_metrics


def test_matrix_axes_class_metrics_and_pr():
    result = chart_metrics([0,0,0,1,1], [0,1,1,0,1], [.1,.6,.7,.3,.9])
    assert result['confusion'] == [[1,2],[1,1]]
    assert result['metrics']['fpr'] == pytest.approx(2/3)
    assert result['classes'][1]['recall'] == .5
    assert sum(c['support'] for c in result['classes']) == 5
    assert all(0 <= r <= 1 and 0 <= p <= 1 for r,p in result['pr_curve'])
