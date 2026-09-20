from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings

engine = create_engine(
    settings.sqlite_url,
    connect_args={"check_same_thread": False},
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def initialize_database(bind):
    """为旧SQLite数据库补列，不改动现有数据；迁移前保留备份。"""
    Base.metadata.create_all(bind=bind)
    additions = {"experiments": {
        "name": "TEXT DEFAULT '训练实验'", "dataset_hash": "TEXT",
        "feature_schema_json": "JSON", "validation_fraction": "FLOAT DEFAULT 0.2",
        "train_rows": "INTEGER", "validation_rows": "INTEGER", "train_seconds": "FLOAT",
        "metrics_json": "JSON", "progress": "INTEGER DEFAULT 0", "logs_json": "JSON DEFAULT '[]'",
        "error": "TEXT", "started_at": "DATETIME", "finished_at": "DATETIME",
        "archived": "BOOLEAN DEFAULT 0",
    }, "detection_tasks": {"normal_count": "INTEGER", "attack_count": "INTEGER"}}
    missing = {}
    for table, definitions in additions.items():
        columns = {c["name"] for c in inspect(bind).get_columns(table)}
        fields = {key: value for key, value in definitions.items() if key not in columns}
        if fields:
            missing[table] = fields
    if missing and bind.dialect.name == "sqlite" and bind.url.database not in (None, ":memory:"):
        import sqlite3
        from pathlib import Path
        path = Path(bind.url.database)
        suffix = "-before-detection-counts" if "detection_tasks" in missing else "-before-experiments"
        backup = path.with_name(path.stem + suffix + ".sqlite3")
        if not backup.exists():
            with sqlite3.connect(path) as source, sqlite3.connect(backup) as target:
                source.backup(target)
    with bind.begin() as connection:
        for table, definitions in missing.items():
            for name, definition in definitions.items():
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))


def get_db():
    """FastAPI 依赖：每个请求使用独立 session。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
