"""报告导出接口：生成含图表的 HTML 报告或 CSV 结果。"""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.detection import completed_task, result_path, stream_result

router = APIRouter()


@router.get("/{task_id}/report")
def export_report(task_id: int, label: int | None = Query(None, ge=0, le=1), db: Session = Depends(get_db)):
    path = result_path(completed_task(db, task_id))
    suffix = "all" if label is None else str(label)
    return StreamingResponse(stream_result(path, label), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="detection-{task_id}-{suffix}.csv"'})
