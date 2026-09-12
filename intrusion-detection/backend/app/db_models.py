"""ORM 模型，对应设计文档第 7 节的表结构。"""
import datetime as dt

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)

from .database import Base


class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    path = Column(String, nullable=False)
    sha256 = Column(String)
    schema_version = Column(String)
    row_count = Column(Integer)
    label_available = Column(Boolean, default=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow)


class Experiment(Base):
    __tablename__ = "experiments"

    id = Column(Integer, primary_key=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"))
    split_version = Column(String)
    algorithm = Column(String)
    params_json = Column(JSON)
    seed = Column(Integer)
    metrics_path = Column(String)
    status = Column(String, default="queued")
    created_at = Column(DateTime, default=dt.datetime.utcnow)


class ModelVersion(Base):
    __tablename__ = "models"

    id = Column(Integer, primary_key=True)
    experiment_id = Column(Integer, ForeignKey("experiments.id"))
    artifact_path = Column(String)
    artifact_hash = Column(String)
    feature_schema = Column(JSON)
    label_map = Column(JSON)
    threshold = Column(Float)
    dependency_versions = Column(JSON)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)


class DetectionTask(Base):
    __tablename__ = "detection_tasks"

    id = Column(Integer, primary_key=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"))
    model_id = Column(Integer, ForeignKey("models.id"))
    status = Column(String, default="queued")
    processed_rows = Column(Integer, default=0)
    total_rows = Column(Integer)
    result_path = Column(String)
    error = Column(Text)
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    created_at = Column(DateTime, default=dt.datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    actor = Column(String)
    action = Column(String)
    target_id = Column(Integer)
    created_at = Column(DateTime, default=dt.datetime.utcnow)