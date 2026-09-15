from contextlib import asynccontextmanager
import json
import pandas as pd

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from ml.prepare import file_sha256

from . import db_models  # noqa: F401  导入以确保建表前注册全部 ORM 模型
from .api import api_router
from .database import Base, engine, initialize_database
from .config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database(engine)
    yield


app = FastAPI(
    title="Intrusion Detection & Visualization System",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(api_router, prefix="/api")


@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    fields = "、".join(dict.fromkeys(str(error["loc"][-1]) for error in exc.errors()))
    return JSONResponse(status_code=422, content={"detail": f"参数校验失败：{fields}。请检查必填项、数值范围与格式"})


@app.get("/api/evaluation")
def evaluation():
    directory = settings.artifacts / "baseline"
    path = directory / "evaluation.json"
    if not path.exists():
        raise HTTPException(404, "尚无评价数据，请运行 python -m ml.cli evaluate")
    data = json.loads(path.read_text(encoding="utf-8"))
    pairs = [(directory / "random_forest.pack_joblib", "model_hash"),
             (directory / "random_forest.pack_meta.json", "meta_hash"),
             (settings.data_raw / "UNSW_NB15_testing-set.csv", "test_hash")]
    if any(not file.exists() or file_sha256(file) != data[key] for file, key in pairs):
        raise HTTPException(409, "模型或数据已变化，请重新生成评价数据")
    return data


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/baseline")
def baseline_status() -> dict:
    """Read the local CLI experiment; this does not submit training jobs."""
    summary = settings.artifacts / "baseline" / "summary.json"
    if not summary.exists():
        return {"ready": False, "summary": None, "preview": []}
    result = settings.data_processed / "demo_predictions.csv"
    preview = pd.read_csv(result, nrows=10).to_dict(orient="records") if result.exists() else []
    return {"ready": True, "summary": json.loads(summary.read_text(encoding="utf-8")), "preview": preview}
