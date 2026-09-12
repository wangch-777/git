"""报告导出接口：生成含图表的 HTML 报告或 CSV 结果。"""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..database import get_db

router = APIRouter()


@router.get("/{task_id}/report")
def export_report(task_id: int, db: Session = Depends(get_db)):
    # TODO: 依据当前筛选与任务生成 HTML 报告（Jinja2）
    return JSONResponse(status_code=501, content={"detail": "报告导出待实现"})