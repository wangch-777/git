"""数据管理接口：上传、校验、字段预览。"""
from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..database import get_db

router = APIRouter()


@router.post("")
def upload_dataset(file: UploadFile = File(...), db: Session = Depends(get_db)):
    # TODO: 校验必需列/类型/缺失值 -> 保存到 data/raw -> 写入 datasets 表
    return JSONResponse(
        status_code=501, content={"detail": "上传与校验逻辑待实现"}
    )


@router.get("/{dataset_id}/preview")
def preview_dataset(dataset_id: int, db: Session = Depends(get_db)):
    # TODO: 返回字段列表与前 N 行样本
    return JSONResponse(
        status_code=501, content={"detail": "字段预览逻辑待实现"}
    )