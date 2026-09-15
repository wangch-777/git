"""数据管理接口：上传、校验、字段预览。"""
from pathlib import Path
import shutil
import pandas as pd
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..config import settings
from ..db_models import Dataset
from ..schemas import DatasetOut
from ..services.detection import MAX_BYTES, new_upload_path, register_dataset

router = APIRouter()


@router.post("", response_model=DatasetOut, status_code=201)
def upload_dataset(file: UploadFile = File(...), db: Session = Depends(get_db)):
    name = Path((file.filename or "").replace("\\", "/")).name
    if not name.lower().endswith(".csv"):
        raise HTTPException(422, "请选择UTF-8编码的CSV文件")
    path = new_upload_path()
    try:
        size = 0
        with path.open("wb") as out:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise HTTPException(413, "文件超过50MB，请拆分后上传")
                out.write(chunk)
        return register_dataset(path, name, db)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        file.file.close()


@router.get("", response_model=list[DatasetOut])
def list_datasets(db: Session = Depends(get_db)):
    return db.query(Dataset).order_by(Dataset.id.desc()).all()


@router.get("/sample")
def download_sample():
    path = settings.data_processed / "demo_input.csv"
    if not path.exists():
        raise HTTPException(404, "示例尚未准备，请先训练基础模型")
    return FileResponse(path, media_type="text/csv", filename="demo_input.csv")


@router.post("/demo", response_model=DatasetOut, status_code=201)
def import_demo(db: Session = Depends(get_db)):
    source = settings.data_processed / "demo_input.csv"
    if not source.exists():
        raise HTTPException(404, "示例尚未准备，请先训练基础模型")
    path = new_upload_path()
    shutil.copyfile(source, path)
    return register_dataset(path, "demo_input.csv", db)


@router.get("/{dataset_id}/preview")
def preview_dataset(dataset_id: int, db: Session = Depends(get_db)):
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(404, "数据集不存在")
    if not Path(dataset.path).exists():
        raise HTTPException(410, "数据文件不存在，请重新上传")
    frame = pd.read_csv(dataset.path, nrows=5)
    return {"columns": frame.columns.tolist(),
            "rows": frame.astype(object).where(pd.notna(frame), None).to_dict(orient="records")}
