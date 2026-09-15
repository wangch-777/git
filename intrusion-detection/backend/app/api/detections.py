"""检测任务接口：创建、查询进度、筛选明细、统计聚合。"""
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import DetectionCreate, DetectionOut
from ..db_models import Dataset, DetectionTask, ModelVersion
from ..services.detection import task_or_404, completed_task, result_path, result_counts, statistics, result_page

router = APIRouter()


@router.post("", response_model=DetectionOut, status_code=201)
def create_detection(payload: DetectionCreate, db: Session = Depends(get_db)):
    dataset = db.get(Dataset, payload.dataset_id)
    model = db.get(ModelVersion, payload.model_id)
    if dataset is None:
        raise HTTPException(404, "数据集不存在")
    if model is None or not model.enabled:
        raise HTTPException(404, "模型不存在或已停用")
    if not Path(dataset.path).exists() or not Path(model.artifact_path).exists():
        raise HTTPException(409, "数据或模型文件缺失，请重新导入或训练")
    task = DetectionTask(dataset_id=dataset.id, model_id=model.id,
                         status="queued", processed_rows=0, total_rows=dataset.row_count)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.get("", response_model=list[DetectionOut])
def list_detections(db: Session = Depends(get_db)):
    return db.query(DetectionTask).order_by(DetectionTask.id.desc()).limit(100).all()


@router.get("/{task_id}", response_model=DetectionOut)
def get_detection(task_id: int, db: Session = Depends(get_db)):
    return task_or_404(db, task_id)


@router.post("/{task_id}/retry", response_model=DetectionOut, status_code=201)
def retry_detection(task_id: int, db: Session = Depends(get_db)):
    old = task_or_404(db, task_id)
    if old.status not in {"failed", "interrupted"}:
        raise HTTPException(409, "只能重试失败或中断的任务")
    return create_detection(DetectionCreate(dataset_id=old.dataset_id, model_id=old.model_id), db)


@router.get("/{task_id}/results")
def list_results(task_id: int, label: int | None = Query(None, ge=0, le=1),
                 page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                 db: Session = Depends(get_db)):
    task = completed_task(db, task_id)
    path = result_path(task)
    normal, attack = result_counts(db, task)
    total = statistics(normal, attack, label)["total"]
    return result_page(path, total, page, page_size, label)


@router.get("/{task_id}/statistics")
def get_statistics(task_id: int, label: int | None = Query(None, ge=0, le=1), db: Session = Depends(get_db)):
    task = completed_task(db, task_id)
    normal, attack = result_counts(db, task)
    return statistics(normal, attack, label)
