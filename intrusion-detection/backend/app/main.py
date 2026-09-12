from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import db_models  # noqa: F401  导入以确保建表前注册全部 ORM 模型
from .api import api_router
from .database import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Intrusion Detection & Visualization System",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(api_router, prefix="/api")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}