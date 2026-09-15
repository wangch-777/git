"""模型管理接口：查询可用模型与协议。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..db_models import ModelVersion, Experiment
from ..services.detection import register_baseline
from ..services.experiments import ALGORITHMS

router = APIRouter()


@router.get("")
def list_models(db: Session = Depends(get_db)):
    try:
        register_baseline(db)
    except HTTPException:
        # 基础模型损坏不应阻止使用已有的实验模型。
        if not db.query(ModelVersion).filter(ModelVersion.experiment_id.isnot(None), ModelVersion.enabled == True).first():
            raise
    result = []
    for model in db.query(ModelVersion).filter_by(enabled=True).order_by(ModelVersion.id.desc()).all():
        experiment = db.get(Experiment, model.experiment_id) if model.experiment_id else None
        name = (f"{ALGORITHMS.get(experiment.algorithm, '模型')} · 实验#{experiment.id} · {experiment.name}"
                if experiment else f"随机森林基础模型 v{model.id}")
        result.append({"id": model.id, "name": name, "experiment_id": model.experiment_id,
             "threshold": model.threshold, "created_at": model.created_at,
             "feature_count": len(model.feature_schema["features"])})
    return result
