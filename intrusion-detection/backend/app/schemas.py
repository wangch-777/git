"""Pydantic 请求/响应模型。"""
import datetime as dt
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class DatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    schema_version: Optional[str] = None
    row_count: Optional[int] = None
    label_available: bool = False
    created_at: dt.datetime


class ExperimentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_id: int
    algorithm: str
    name: str = Field(default="训练实验", min_length=1, max_length=100)
    params: dict[str, Any] = Field(default_factory=dict)
    seed: int = Field(default=42, ge=0, le=2147483647)
    validation_fraction: float = Field(default=0.2, ge=0.1, le=0.4)


class ExperimentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)


class DetectionCreate(BaseModel):
    dataset_id: int
    model_id: int


class DetectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dataset_id: int
    model_id: int
    status: str
    processed_rows: int = 0
    total_rows: Optional[int] = None
    error: Optional[str] = None
    started_at: Optional[dt.datetime] = None
    finished_at: Optional[dt.datetime] = None
