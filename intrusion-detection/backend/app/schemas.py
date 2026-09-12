"""Pydantic 请求/响应模型。"""
import datetime as dt
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class DatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    schema_version: Optional[str] = None
    row_count: Optional[int] = None
    label_available: bool = False
    created_at: dt.datetime


class ExperimentCreate(BaseModel):
    dataset_id: int
    split_version: str = "v1"
    algorithm: str
    params: dict[str, Any] = {}
    seed: int = 42


class DetectionCreate(BaseModel):
    dataset_id: int
    model_id: int


class DetectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    processed_rows: int = 0
    total_rows: Optional[int] = None
    error: Optional[str] = None
    started_at: Optional[dt.datetime] = None
    finished_at: Optional[dt.datetime] = None