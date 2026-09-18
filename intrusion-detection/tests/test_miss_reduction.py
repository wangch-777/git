import numpy as np
import pandas as pd
import pytest

from ml.calibration import fit_platt, log_odds, working_points, PlattClassifier
from ml.miss_reduction import clean, choose, finalize, prior_weights
from ml.predict import predict_dataframe
from ml.registry import load_model_pack
from ml.train import fit_model, save_model_pack_from_fit
from tests.test_detection_flow import flow, create_task


def test_conflict_policies_preserve_truth_and_ties():
    frame=pd.DataFrame({'x':[1,1,1,2,2,3,3], 'label':[0,0,1,0,1,1,1]})
    drop,a=clean(frame,['x'],'drop_conflicts')
    majority,b=clean(frame,['x'],'majority')
    first,c=clean(frame,['x'],'keep_first')
    assert drop.index.tolist()==[5,6]
    assert majority.index.tolist()==[0,1,5,6]
    assert first.index.tolist()==[0,3,5]
    assert a['conflict_groups']==2 and b['tie_groups']==1 and c['removed']==4
    assert majority.label.tolist()==frame.loc[majority.index].label.tolist()


def test_prior_target_is_weighted_55_percent():
    labels=pd.Series([0]*30+[1]*70)
    weights=prior_weights(labels,'target_55')
    assert 70*weights[1]/(70*weights[1]+30*weights[0])==pytest.approx(.55)


def test_cost_threshold_matches_exhaustive_grid_and_boundary():
    labels=np.array([0,0,0,1,1,1])
    score=np.array([.1,.4,.8,.4,.7,.9])
    points,_=working_points(labels,score,max_fnr=0)
    assert np.mean(score[labels==1]<points['fnr_constraint'])==0
    for cost in (1,5,10):
        def loss(t):
            return cost*np.sum((labels==1)&(score<t))+np.sum((labels==0)&(score>=t))
        assert loss(points[f'cost_{cost}'])==min(loss(t) for t in [0,.1,.4,.7,.8,.9,1])


def test_calibrated_pack_roundtrip_uses_calibrated_selected_score(tmp_path):
    X=pd.DataFrame({'dur':[1.,2.,3.,4.]})
    pipe=fit_model(X,pd.Series([0,0,1,1]),'decision_tree',{'max_depth':1})
    mapper=fit_platt(np.linspace(.1,.9,20),np.array([0]*10+[1]*10))
    wrapper=PlattClassifier(pipe.named_steps['classifier'],mapper)
    pipe.steps[-1]=('classifier',wrapper)
    path=save_model_pack_from_fit(pipe,['dur'],{'0':'正常','1':'攻击'},.5,tmp_path,{'name':'calibrated'})
    pack=load_model_pack(path)
    result=predict_dataframe(pack,X)
    p=pipe.predict_proba(X)
    assert result.predicted_label.tolist()==[0,0,1,1]
    np.testing.assert_allclose(result.score,[p[i,label] for i,label in enumerate(result.predicted_label)])
    assert np.isfinite(log_odds([0,1])).all()


def test_model_selection_ignores_test_and_repeat_finalization_blocked(tmp_path):
    candidates=[{'id':'a','validation':{'fnr_constraint':{'fpr':.1,'fnr':.02,'ap':.9}},'test':{'fpr':.9}},
                {'id':'b','validation':{'fnr_constraint':{'fpr':.2,'fnr':.01,'ap':.95}},'test':{'fpr':0}}]
    assert choose(candidates)['id']=='a'
    (tmp_path/'test-started.json').write_text('{}')
    with pytest.raises(ValueError,match='拒绝重复'):
        finalize(tmp_path)


def test_worker_loads_calibrated_pack_without_changing_output_contract(flow):
    from backend.app.config import settings
    from backend.app.db_models import DetectionTask
    from ml.registry import save_model_pack
    from worker import worker
    client,sessions=flow
    source=settings.artifacts/'baseline/random_forest.pack_joblib'
    pack=load_model_pack(source)
    mapper=fit_platt(np.linspace(.1,.9,20),np.array([0]*10+[1]*10))
    wrapper=PlattClassifier(pack['classifier'],mapper)
    save_model_pack(source.parent,pack['preprocessor'],wrapper,pack['meta']['feature_list'],
                    pack['meta']['label_map'],.4,{'name':'random_forest','calibration':{'method':'Platt'}})
    task_id=create_task(client)
    assert worker.run_once()
    with sessions() as db:
        task=db.get(DetectionTask,task_id)
        assert task.status=='succeeded'
        output=pd.read_csv(task.result_path)
    expected=predict_dataframe(load_model_pack(source),pd.read_csv(settings.data_processed/'demo_input.csv'))
    np.testing.assert_array_equal(output.predicted_label,expected.predicted_label)
    np.testing.assert_allclose(output.score,expected.score)
    assert list(output.columns)==['source_row_id','predicted_label','predicted_name','score']
