"""检测任务接口：创建、查询进度、筛选明细、统计聚合。"""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import DetectionCreate

router = APIRouter()


@router.post("")
def create_detection(payload: DetectionCreate, db: Session = Depends(get_db)):
    # TODO: 校验模型协议 -> 写入 detection_tasks(status=queued)
    return JSONResponse(status_code=501, content={"detail": "检测任务创建待实现"})


@router.get("/{task_id}")
def get_detection(task_id: int, db: Session = Depends(get_db)):
    # TODO: 返回进度与摘要
    return JSONResponse(status_code=501, content={"detail": "检测进度查询待实现"})


@router.get("/{task_id}/results")
def list_results(task_id: int, db: Session = Depends(get_db)):
    # TODO: 按任务、模型、预测类别、分数分页筛选明细
    return JSONResponse(status_code=501, content={"detail": "检测明细查询待实现"})


@router.get("/{task_id}/statistics")
def get_statistics(task_id: int, db: Session = Depends(get_db)):
    # TODO: 当前筛选条件下的统计聚合
    return JSONResponse(status_code=501, content={"detail": "统计聚合待实现"})