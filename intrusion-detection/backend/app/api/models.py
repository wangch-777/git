"""模型管理接口：查询可用模型与协议。"""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..database import get_db

router = APIRouter()


@router.get("")
def list_models(db: Session = Depends(get_db)):
    # TODO: 返回启用中的模型版本、特征协议与标签映射
    return JSONResponse(status_code=501, content={"detail": "模型列表待实现"})