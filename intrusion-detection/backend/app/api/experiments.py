"""实验管理接口：创建训练任务、查询状态与结果。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import ExperimentCreate, ExperimentUpdate, DatasetOut
from ..db_models import Experiment, ModelVersion
from ..services.experiments import create, serialize, find_experiment, sample_dataset

router = APIRouter()


@router.post("", status_code=201)
def create_experiment(payload: ExperimentCreate, db: Session = Depends(get_db)):
    return serialize(db, create(db, payload))


@router.get("")
def list_experiments(db: Session = Depends(get_db)):
    return [serialize(db, item) for item in db.query(Experiment).filter_by(archived=False).order_by(Experiment.id.desc()).all()]


@router.post("/sample", response_model=DatasetOut, status_code=201)
def prepare_sample(db: Session = Depends(get_db)):
    return sample_dataset(db)


@router.get("/{experiment_id}")
def get_experiment(experiment_id: int, db: Session = Depends(get_db)):
    return serialize(db, find_experiment(db, experiment_id))


@router.patch("/{experiment_id}")
def update_experiment(experiment_id: int, payload: ExperimentUpdate, db: Session = Depends(get_db)):
    item = find_experiment(db, experiment_id)
    if not payload.name.strip():
        raise HTTPException(422, "实验名称不能为空")
    item.name = payload.name.strip()
    db.commit()
    return serialize(db, item)


@router.delete("/{experiment_id}")
def delete_experiment(experiment_id: int, db: Session = Depends(get_db)):
    item = find_experiment(db, experiment_id)
    if item.status == "running":
        raise HTTPException(409, "训练中的实验不能删除，请等待完成")
    changed = db.execute(update(Experiment).where(Experiment.id == experiment_id, Experiment.status != "running",
                         Experiment.archived == False).values(archived=True))
    if not changed.rowcount:
        db.rollback()
        raise HTTPException(409, "实验已开始训练，请等待完成")
    db.query(ModelVersion).filter_by(experiment_id=experiment_id).update({"enabled": False})
    db.commit()
    return {"message": "实验已从列表移除，历史检测及模型文件保留"}


@router.post("/{experiment_id}/retry", status_code=201)
def retry_experiment(experiment_id: int, db: Session = Depends(get_db)):
    item = find_experiment(db, experiment_id)
    if item.status not in {"failed", "interrupted"}:
        raise HTTPException(409, "只能重试失败或中断的实验")
    payload = ExperimentCreate(dataset_id=item.dataset_id, algorithm=item.algorithm, name=item.name,
        params={key: value for key, value in item.params_json.items() if key not in {"random_state", "n_jobs"}},
        seed=item.seed, validation_fraction=item.validation_fraction)
    return serialize(db, create(db, payload))
