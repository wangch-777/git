"""实验管理接口：创建训练任务、查询状态与结果。"""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import ExperimentCreate

router = APIRouter()


@router.post("")
def create_experiment(payload: ExperimentCreate, db: Session = Depends(get_db)):
    # TODO: 写入 experiments(status=queued)，由 Worker 领取执行训练
    return JSONResponse(status_code=501, content={"detail": "训练任务创建待实现"})


@router.get("/{experiment_id}")
def get_experiment(experiment_id: int, db: Session = Depends(get_db)):
    # TODO: 查询任务状态与评估结果
    return JSONResponse(status_code=501, content={"detail": "实验查询待实现"})